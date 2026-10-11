import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .asof import validate_asof
from .backtest import run_backtest
from .clock import clock_for
from .config import CONFIG, ENV_OVERRIDES_USED, paper_api_key
from .ids import token_key as _token_key
from .models import BacktestRequest, PaperBarRequest, PaperSignalRequest, ScoreRequest, WalkForwardRequest, WalletPnlRequest
from .pnl import compute_pnl, to_jsonable
from .paper import API_EXIT_REASONS, timeframe_seconds
from .scoring import evaluate_cohort
from .walkforward import walk_forward
from .security import AuthThrottle, BodyLimitMiddleware
from .store import store_from_env

log = logging.getLogger("smartcopy")


def sweep_once(app) -> list:
    """Close expired positions. Cheap read first, so an idle loop never takes the portfolio lock or rewrites rows."""
    store, clock = app.state.store, app.state.clock
    with store.read() as p:
        now = clock.now(p)
        due = any(x.get("expires_ts") is not None and x["expires_ts"] <= now for x in p.positions.values())
    if not due:
        return []
    with store.txn() as s:
        return s.portfolio.sweep_expired(clock.now(s.portfolio))


def create_app(store=None, clock=None, sweep_interval=None, max_body_bytes=None) -> FastAPI:
    interval = CONFIG.paper_sweep_interval_sec if sweep_interval is None else sweep_interval

    async def sweep_loop(app):
        while True:
            await asyncio.sleep(interval)
            try:
                closed = await run_in_threadpool(sweep_once, app)
                if closed:
                    log.info("sweeper closed %d expired position(s)", len(closed))
            except Exception:  # noqa: BLE001  (a DB outage must not kill the loop; it retries next tick)
                log.warning("sweeper tick failed", exc_info=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store if store is not None else store_from_env()
        app.state.clock = clock if clock is not None else clock_for(CONFIG.paper_clock)
        task = None
        if interval > 0 and app.state.clock.name == "live":
            task = asyncio.create_task(sweep_loop(app))
        try:
            yield
        finally:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    app = FastAPI(title="Smart Copy Trading Research API", version="0.4.5", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)       # no public schema/UI
    app.state.throttle = AuthThrottle(CONFIG.auth_fail_limit, CONFIG.auth_fail_window_sec)
    app.add_middleware(BodyLimitMiddleware, limit=CONFIG.max_body_bytes if max_body_bytes is None else max_body_bytes)

    # ------------------------------------------------------------------ error handling
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # Standard 422 body. `input`/`ctx` are dropped: they may hold NaN/Infinity or huge payloads that cannot be
        # serialised as strict JSON (which used to turn a bad request into a 500).
        errs = [{"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))}
                for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errs})

    @app.exception_handler(psycopg.OperationalError)
    @app.exception_handler(psycopg.InterfaceError)
    @app.exception_handler(psycopg.errors.ReadOnlySqlTransaction)
    async def storage_unavailable(request: Request, exc: Exception):
        log.error("storage unavailable: %s", type(exc).__name__)          # class only: never log DSN / driver text
        return JSONResponse(status_code=503, content={"detail": "storage unavailable"}, headers={"Retry-After": "5"})

    @app.exception_handler(psycopg.Error)
    async def storage_error(request: Request, exc: Exception):
        log.error("storage error: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "internal storage error"})

    # ------------------------------------------------------------------ auth (every route except /health)
    def auth(request: Request, x_research_key: str = Header(default="")) -> None:
        expected = paper_api_key()
        if not expected:
            raise HTTPException(503, "PAPER_API_KEY is not configured; the research API is disabled")
        client = request.client.host if request.client else "unknown"
        wait = request.app.state.throttle.retry_after(client)
        if wait:
            raise HTTPException(429, "too many failed authentication attempts", headers={"Retry-After": str(wait)})
        if not hmac.compare_digest(x_research_key.encode(), expected.encode()):
            request.app.state.throttle.failure(client)
            raise HTTPException(401, "invalid research API key")
        request.app.state.throttle.success(client)

    secured = [Depends(auth)]

    def S(request: Request):
        return request.app.state.store

    def now_for(request: Request, portfolio) -> int:
        return request.app.state.clock.now(portfolio)

    def check_asof(request, portfolio, wallets, signal_ts):
        try:
            validate_asof(wallets, signal_ts, now_for(request, portfolio))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def check_chain(chain, wallets):
        if any(w.chain.lower() != chain.lower() for w in wallets):
            raise HTTPException(422, "wallet chain does not match signal chain")

    # ------------------------------------------------------------------ public liveness
    @app.get("/health")
    def health(request: Request):
        ok = S(request).ping()
        body = {"status": "ok" if ok else "degraded", "mode": "research/paper", "live_execution": CONFIG.live_execution}
        if not ok:
            raise HTTPException(503, body)
        return body

    # ------------------------------------------------------------------ read (authenticated)
    @app.get("/status", dependencies=secured)
    def status(request: Request):
        st = S(request)
        return {"store": st.name, "persistent": st.persistent, "clock": request.app.state.clock.name,
                "sweep_interval_sec": CONFIG.paper_sweep_interval_sec, "config_sha256": CONFIG.sha256()}

    @app.get("/config", dependencies=secured)
    def config():
        return {**CONFIG.as_dict(), "config_sha256": CONFIG.sha256(), "env_overrides": list(ENV_OVERRIDES_USED)}

    @app.post("/score", dependencies=secured)
    def score(req: ScoreRequest, request: Request):
        check_chain(req.chain, req.wallets)
        with S(request).read() as p:
            check_asof(request, p, req.wallets, req.signal_ts)
        ev = evaluate_cohort(req.wallets, req.liquidity_usd)
        return {"chain": req.chain, "token": req.token, "signal_ts": req.signal_ts, **ev}

    @app.post("/backtest", dependencies=secured)
    def backtest(req: BacktestRequest):
        return run_backtest(req)

    @app.post("/backtest/walkforward", dependencies=secured)
    def backtest_walkforward(req: WalkForwardRequest):
        try:
            return walk_forward(req.base, train_frac=req.train_frac, val_frac=req.val_frac, target_grid=tuple(req.target_grid),
                                stop_grid=tuple(req.stop_grid), min_trades=req.min_trades,
                                latency_grid=tuple(req.latency_grid), slippage_grid=tuple(req.slippage_grid))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/wallet/pnl", dependencies=secured)
    def wallet_pnl(req: WalletPnlRequest):
        """Realised/unrealised PnL of a wallet ledger (fees, transfers, initial balances, oversells, data errors)."""
        if any(not (m >= 0 and m < 1e18) for m in req.marks.values()):
            raise HTTPException(422, "marks must be finite, >= 0")
        res = compute_pnl([e.model_dump(exclude_none=True) for e in req.entries],
                          initial_balances={k: v.model_dump(exclude_none=True) for k, v in req.initial_balances.items()},
                          method=req.method, marks=req.marks, transfer_in_policy=req.transfer_in_policy,
                          transfer_out_policy=req.transfer_out_policy)
        return to_jsonable(res)

    @app.get("/paper", dependencies=secured)
    def paper_status(request: Request, limit: int = 50):
        st = S(request)
        limit = max(1, min(limit, 500))
        with st.read() as p:
            drift = {k: {"stored": getattr(p, k), "configured": v} for k, v in
                     (("slippage_bps", CONFIG.paper_slippage_bps), ("fee_bps", CONFIG.paper_fee_bps),
                      ("gas_usd", CONFIG.paper_gas_usd)) if getattr(p, k) != v}
            return {"portfolio": p.snapshot(), "positions": p.positions,
                    "price_book": {k: {"price": v, "price_ts": p.last_price_ts[k]} for k, v in p.last_prices.items()},
                    "cooldowns": p.cooldown_until, "assumption_drift": drift,
                    "closed_trades": st.recent_closed_trades(limit), "fills": st.recent_fills(limit)}

    @app.post("/paper/mark", dependencies=secured)
    def paper_mark(request: Request):
        with S(request).read() as p:                       # observational: never writes
            return p.snapshot()

    # ------------------------------------------------------------------ write (authenticated)
    @app.post("/paper/replay/bar", dependencies=secured)
    def paper_replay_bar(req: PaperBarRequest, request: Request):
        if req.timeframe != CONFIG.paper_bar_timeframe:
            raise HTTPException(422, f"only timeframe {CONFIG.paper_bar_timeframe!r} is accepted")
        tf = timeframe_seconds(req.timeframe)
        if req.ts % tf:
            raise HTTPException(422, "bar ts must be aligned to the timeframe")
        key, bar_end = _token_key(req.chain, req.token), req.ts + tf
        bar = {"ts": req.ts, "end_ts": bar_end, "timeframe": req.timeframe, "open": req.open, "high": req.high,
               "low": req.low, "close": req.close, "volume_usd": req.volume_usd}
        with S(request).txn() as s:
            p = s.portfolio
            if request.app.state.clock.name == "live" and bar_end > now_for(request, p) + CONFIG.signal_clock_skew_sec:
                raise HTTPException(422, "bar is not complete yet")
            last = p.last_bar_ts.get(key)
            if last is not None and req.ts < last:
                raise HTTPException(409, "out-of-order bar")
            if last is not None and req.ts == last:
                old = s.get_bar(key, req.timeframe, req.ts)
                same = old is not None and all(abs(old[k] - bar[k]) < 1e-12 for k in
                                               ("open", "high", "low", "close", "volume_usd"))
                if same:
                    return {"status": "duplicate", "token_key": key, "bar_ts": req.ts, "portfolio": p.snapshot()}
                raise HTTPException(409, "conflicting duplicate bar: completed bars are immutable")
            s.record_bar(key, bar)
            outcome = p.evaluate_bar(key, bar) if key in p.positions else {"status": "no_position"}
            p.update_market_price(key, req.close, bar_end)
            p.last_bar_ts[key] = req.ts
            return {"status": "accepted", "token_key": key, "bar_ts": req.ts, "price_ts": bar_end,
                    "bar_evaluation": outcome, "portfolio": p.snapshot()}

    @app.post("/paper/signal", dependencies=secured)
    def paper_signal(req: PaperSignalRequest, request: Request):
        check_chain(req.chain, req.wallets)
        key = _token_key(req.chain, req.token)
        with S(request).txn() as s:
            p = s.portfolio
            now = now_for(request, p)
            check_asof(request, p, req.wallets, req.signal_ts)
            ev = evaluate_cohort(req.wallets, req.liquidity_usd)
            reasons, result = list(ev["reasons"]), None
            if ev["signal_valid"] and not p.can_enter(ev["cohort_score"], ev["confidence"],
                                                      ev["independent_confirmations"], req.liquidity_usd):
                reasons.append("guardrails_not_met")
            if not reasons:
                price_ts = p.last_price_ts.get(key)
                if price_ts is None or now - price_ts > CONFIG.max_market_price_age_sec:
                    reasons.append("no_fresh_trusted_market_price")
            if not reasons:
                result = p.enter(key, None, req.allocation_pct, target_return_pct=req.target_return_pct,
                                 stop_loss_pct=req.stop_loss_pct, max_hold_sec=req.max_hold_sec)
                if result["status"] != "entered":
                    reasons.append(result["status"])
            entered = result is not None and result["status"] == "entered"
            sid = s.record_signal(token_key=key, signal_ts=req.signal_ts,
                                  stats_as_of_ts=min(w.as_of_ts for w in req.wallets) if req.wallets else req.signal_ts,
                                  wallet_count=len(req.wallets), score=ev["cohort_score"],
                                  confidence=ev["confidence"], action="ENTER" if entered else "WAIT",
                                  reasons=reasons)
            if entered:
                p.positions[key]["signal_id"] = sid
                p.new_fills[-1]["signal_id"] = sid
                return {"action": "ENTER", "signal_id": sid, **result, "evaluation": ev}
            out = {"action": "WAIT", "signal_id": sid, "reasons": reasons, "evaluation": ev}
            if result is not None:
                out["status"] = result["status"]
                out.update({k: v for k, v in result.items() if k != "status"})
            return out

    @app.post("/paper/exit/{chain}/{token}", dependencies=secured)
    def paper_exit(chain: str, token: str, request: Request, reason: str = "manual"):
        if reason not in API_EXIT_REASONS:
            raise HTTPException(422, f"reason must be one of {sorted(API_EXIT_REASONS)}; "
                                     "stop/target/time are engine-only")
        key = _token_key(chain, token)
        with S(request).txn() as s:
            p = s.portfolio
            if key not in p.positions:
                raise HTTPException(404, "position not found")
            price_ts = p.last_price_ts.get(key)
            if price_ts is None or now_for(request, p) - price_ts > CONFIG.max_market_price_age_sec:
                raise HTTPException(503, "no fresh trusted market price available")
            return p.exit(key, p.last_prices[key], reason)

    @app.post("/paper/sweep", dependencies=secured)
    def paper_sweep(request: Request):
        """Close time-expired positions now (idempotent). Used by the background loop, cron, or by hand."""
        closed = sweep_once(request.app)
        return {"swept": len(closed), "closed": closed}

    return app


app = create_app()
