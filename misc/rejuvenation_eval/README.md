## Usage instructions:

```bash
cd misc/rejuvenation_eval
# example usage of creating 2 instances in us-east-1 with UM account: 
# explanation of above example: this creates 2 instances in the us-east-1a az, in the UM AWS account
python3 rejuvenation-eval-script.py data/setup1/input-args.json # create a new dir for each distinct experiment parameters..
```

## Other script explanations:
1. Perform a bunch of remaps (moving EIP from one instance to another) to emperically validate how remap charges work. Reason: our disassociate/associate/allocate/deallocate functions did not trigger remapping cost in cost explorer at all..
```bash
python3 random-test-random.py
```
2. Just pulled out the calculate_cost function from rejuvenation-eval-script to manually get cost values.. Not really used script, deprecated for now.
```bash
python3 misc/calculate-cost.py
```