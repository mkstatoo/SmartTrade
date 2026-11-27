# Provider probe

UTC: 2026-11-27 22:52:15

| chain | provider | usable | max getLogs range | p50 ms | p95 ms | burst errors /30 | depth 10k/100k/1M | agrees | first error |
|---|---|---|---|---|---|---|---|---|---|
| ethereum | publicnode | True | 1 | 50 | 59 | 0 | Y/Y/Y | True |  |
| ethereum | llamarpc | False | None | None | None | None | - | None | RpcError: HTTP 525: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| ethereum | cloudflare | False | None | None | None | None | - | None | RpcError: Cannot fulfill request |
| ethereum | ankr | False | None | None | None | None | - | None | RpcError: malformed or mismatched JSON-RPC response: {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: You mu |
| ethereum | drpc | True | 10 | 25 | 28 | 0 | Y/Y/Y | True |  |
| ethereum | 1rpc | False | 0 | 168 | 583 | 3 | N/N/Y | None | headers: RpcError: HTTP 429: {"jsonrpc":"2.0","id":null,"error":{"code":-32005,"message":"You have reached the maximum API usage  |
| ethereum | private-1 | False | None | None | None | None | - | None | RpcError: transport error: URLError |
| ethereum | private-2 | False | None | None | None | None | - | None | RpcError: transport error: URLError |
| base | base-official | False | 0 | 41 | 49 | 0 | Y/Y/Y | None |  |
| base | publicnode | True | 1 | 54 | 59 | 0 | Y/Y/Y | True |  |
| base | llamarpc | False | None | None | None | None | - | None | RpcError: HTTP 525: {"type":"https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx- |
| base | ankr | False | None | None | None | None | - | None | RpcError: malformed or mismatched JSON-RPC response: {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized: You mu |
| base | drpc | False | 0 | 24 | 38 | 21 | N/N/N | None | headers: RpcError: HTTP 429: {"id":43,"jsonrpc":"2.0","error":{"message":"You reached Public endpoint rate limit, please upgrade  |
| base | 1rpc | True | 10 | 178 | 969 | 0 | Y/Y/Y | None | agreement fetch: HTTP 410: {"error":"This endpoint has been discontinued.","message":"For an up to date list of available endpo |
| base | private-1 | True | 500 | 89 | 135 | 0 | Y/Y/Y | True |  |

## Selection
```
{
 "ethereum": {
  "ranked": [
   "drpc",
   "publicnode"
  ],
  "primary": "drpc",
  "verifier": "publicnode",
  "ranges": {
   "drpc": 10,
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
