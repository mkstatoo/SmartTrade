# Provider probe

UTC: 2026-11-01 21:23:17

| chain | provider | usable | max getLogs range | p50 ms | p95 ms | burst errors /30 | depth 10k/100k/1M | agrees | first error |
|---|---|---|---|---|---|---|---|---|---|
| ethereum | publicnode | True | 1 | 303 | 317 | 0 | Y/Y/Y | True |  |
| ethereum | llamarpc | False | None | None | None | None | - | None | RpcError: HTTP 525: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| ethereum | cloudflare | False | None | None | None | None | - | None | RpcError: Cannot fulfill request |
| ethereum | ankr | False | None | None | None | None | - | None | RpcError: malformed or mismatched JSON-RPC response: {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: You mu |
| ethereum | drpc | True | 10 | 311 | 395 | 0 | Y/Y/Y | True |  |
| ethereum | 1rpc | False | None | None | None | None | - | None | RpcError: HTTP 503: {"jsonrpc":"2.0","result":{"code":503,"message":"server unavailable"},"id":2} |
| ethereum | private-1 | True | 1 | 365 | 422 | 0 | Y/Y/Y | True |  |
| ethereum | private-2 | True | 1 | 365 | 425 | 0 | Y/Y/Y | True |  |
| base | base-official | False | 0 | 136 | 178 | 0 | Y/Y/Y | None |  |
| base | publicnode | True | 1 | 309 | 498 | 0 | Y/Y/Y | True |  |
| base | llamarpc | False | None | None | None | None | - | None | RpcError: HTTP 525: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| base | ankr | False | None | None | None | None | - | None | RpcError: malformed or mismatched JSON-RPC response: {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: You mu |
| base | drpc | True | 10 | 311 | 315 | 0 | Y/Y/Y | True |  |
| base | 1rpc | False | 10 | 1411 | 1534 | 1 | Y/Y/Y | None | headers: RpcError: HTTP 410: {"error":"This endpoint has been discontinued.","message":"For an up to date list of available endpo |
| base | private-1 | True | 10 | 360 | 734 | 0 | Y/Y/Y | True |  |

## Selection
```
{
 "ethereum": {
  "ranked": [
   "drpc",
   "private-1",
   "private-2",
   "publicnode"
  ],
  "primary": "drpc",
  "verifier": "private-1",
  "ranges": {
   "drpc": 10,
   "private-1": 1,
   "private-2": 1,
   "publicnode": 1
  }
 },
 "base": {
  "ranked": [
   "private-1",
   "drpc",
   "publicnode"
  ],
  "primary": "private-1",
  "verifier": "drpc",
  "ranges": {
   "private-1": 10,
   "drpc": 10,
   "publicnode": 1
  }
 }
}
```
