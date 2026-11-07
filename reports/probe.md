# Provider probe

UTC: 2026-11-07 11:07:53

| chain | provider | usable | max getLogs range | p50 ms | p95 ms | burst errors /30 | depth 10k/100k/1M | agrees | first error |
|---|---|---|---|---|---|---|---|---|---|
| ethereum | publicnode | True | 1 | 67 | 90 | 0 | Y/Y/Y | True |  |
| ethereum | llamarpc | False | None | None | None | None | - | None | RpcError: HTTP 525: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| ethereum | cloudflare | False | None | None | None | None | - | None | RpcError: Cannot fulfill request |
| ethereum | ankr | False | None | None | None | None | - | None | RpcError: malformed or mismatched JSON-RPC response: {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: You mu |
| ethereum | drpc | True | 10 | 42 | 49 | 0 | Y/Y/Y | True |  |
| ethereum | 1rpc | False | 10 | 180 | 421 | 0 | Y/Y/Y | None | headers: RpcError: HTTP 410: {"error":"This endpoint has been discontinued.","message":"For an up to date list of available endpo |
| ethereum | private-1 | True | 1 | 178 | 391 | 0 | Y/Y/Y | True |  |
| ethereum | private-2 | True | 1 | 165 | 184 | 0 | Y/Y/Y | True |  |
| base | base-official | False | 0 | 62 | 66 | 0 | Y/Y/Y | None |  |
| base | publicnode | True | 1 | 68 | 78 | 0 | Y/Y/Y | True |  |
| base | llamarpc | False | None | None | None | None | - | None | RpcError: HTTP 525: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| base | ankr | False | None | None | None | None | - | None | RpcError: malformed or mismatched JSON-RPC response: {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: You mu |
| base | drpc | False | 0 | 44 | 56 | 9 | N/N/N | None | headers: RpcError: HTTP 429: {"id":43,"jsonrpc":"2.0","error":{"message":"You reached Public endpoint rate limit, please upgrade  |
| base | 1rpc | False | 10 | 114 | 284 | 0 | Y/Y/Y | None | headers: RpcError: HTTP 410: {"error":"This endpoint has been discontinued.","message":"For an up to date list of available endpo |
| base | private-1 | True | 500 | 110 | 243 | 0 | Y/Y/Y | True |  |

## Selection
```
{
 "ethereum": {
  "ranked": [
   "drpc",
   "private-2",
   "private-1",
   "publicnode"
  ],
  "primary": "drpc",
  "verifier": "private-2",
  "ranges": {
   "drpc": 10,
   "private-2": 1,
   "private-1": 1,
   "publicnode": 1
  }
 },
 "base": {
  "ranked": [
   "private-1",
   "publicnode"
  ],
  "primary": "private-1",
  "verifier": "publicnode",
  "ranges": {
   "private-1": 500,
   "publicnode": 1
  }
 }
}
```
