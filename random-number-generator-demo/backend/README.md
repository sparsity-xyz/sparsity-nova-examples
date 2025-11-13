# RNG backend

## start
```
python3 main.py
```

## steps
when the service start, you need to deposit the address inside service 
and register it as an operator in contract

### get address inside service
```
curl http://localhost:8000/
```
the output should be
```
{
    "service": "Random Number Generator",
    "version": "1.0.0",
    "status": "running",
    "is_operator": true,
    "contract_address": "0xB7f8BC63BbcaD18155201308C8f3540b07f84F5e",
    "operator": "0xAae4260D8b9AE1D2D6fBC07FCE0D9a46852c5984",
    "operator_balance": 0.998857,
    "processed_requests": 0
}
```
### deposit and register the address
use `operator` above
