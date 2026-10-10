"""CLI:  CHAIN_RPC_URL=https://... DATABASE_URL=... python -m app.chain --chain eth [--start-block N] [--confirmations 12]
The RPC URL is read from the environment only (it normally contains an API key) and is never printed or stored."""
import argparse
import os
import sys

from app.chain.ingest import IngestError, ingest
from app.chain.rpc import JsonRpcSource, RpcError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.chain")
    ap.add_argument("--chain", required=True)
    ap.add_argument("--start-block", type=int)
    ap.add_argument("--confirmations", type=int, default=12)
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--max-blocks", type=int)
    ap.add_argument("--address", action="append", help="restrict to this contract (repeatable, lower-case 0x…)")
    a = ap.parse_args(argv)
    url, dsn = os.getenv("CHAIN_RPC_URL"), os.getenv("DATABASE_URL")
    if not url or not dsn:
        print("CHAIN_RPC_URL and DATABASE_URL are required", file=sys.stderr)
        return 2
    try:
        r = ingest(JsonRpcSource(url), dsn, a.chain, start_block=a.start_block, confirmations=a.confirmations,
                   batch=a.batch, max_blocks=a.max_blocks, addresses=a.address)
    except (IngestError, RpcError, ValueError) as exc:
        print(f"ingest failed: {exc}", file=sys.stderr)
        return 1
    print(f"chain={r.chain} blocks={r.blocks} logs={r.logs} decoded={r.decoded} decode_errors={r.decode_errors} "
          f"reorgs={r.reorgs} next_block={r.next_block} head={r.head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
