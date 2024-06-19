import math

def calculate_cost(instance_list, rej_period, exp_duration, multi_NIC=True, rej_count=None, ephemeral_charge=False):
    """
        Parameters:
            - instance_list:
                [
                    {
                        'InstanceID': instance_id,
                        'InstanceType': instance_type,
                        'InstanceCost': float,
                        'NICs': [(NIC ID, EIP ID, ASSOCIATION ID), ...]
                    },
                    ...
                ]
                - Note: in instance rejuvenation, this list will contain all the instances that were created for each rejuvenation event. 
            - exp_duration: in minutes
            - rej_period: in seconds
            - rej_count: used for live ip rejuvenation only. Number of rejuvenation events that occurred. 
            - ephemeral_charge: False | True
                - False means we are using the old/current cost model where ephemeral IPs are free (note that for Live IP there is no ephemeral IP because we need to use eips for this form of rejuvenation)
                - True means we are using the new cost model (upcoming ~Feb for AWS) where where even the ephemeral IP is charged at $0.005/hr

        Explanation:
            - Done in the style of skypilot.
                - Here's how they do it (in order of increasing detail):
                    - "SPENT($)" is what they use in their benchmark tool: https://github.com/skypilot-org/skypilot/blob/c1f28bcb630b60f9a22d2303119f7ce62e700de3/docs/source/reference/benchmark/cli.rst#id1
                    - which internally is populated by the resource.get_cost(duration) function: https://github.com/skypilot-org/skypilot/blob/c1f28bcb630b60f9a22d2303119f7ce62e700de3/sky/cli.py#L5087
                    - which in turn is calculated using their catalogue cost model of the instance hourly pricing: https://github.com/skypilot-org/skypilot/blob/c1f28bcb630b60f9a22d2303119f7ce62e700de3/sky/resources.py#L875
                    - as shown here: https://github.com/skypilot-org/skypilot/blob/c1f28bcb630b60f9a22d2303119f7ce62e700de3/sky/clouds/aws.py#L286
                - Some extra info: we actually go a little further than skypilot, because: "SkyPilot Benchmark does not consider the time/cost of provisioning and setup." https://github.com/skypilot-org/skypilot/blob/c1f28bcb630b60f9a22d2303119f7ce62e700de3/docs/source/reference/benchmark/cli.rst#id1
            - This is the only way since real time cost output is not provided by cloud providers (e.g., take 24 hours to be reflected).
            - With that said however, we've done due diligence, by checking that our cost results here match that observed in cost explorers reflected after a day or so. 
                - In other word, we actually ran the experiments, not just building them off of simulated cost models. 
            - Why am I going through this trouble? Because even after 24 hours, the cost explorer did not populate the instance costs for instances that were only run for a few mins... but it did for the instance that ran for ~1 hours (with tag "test-delete-cost-explorer-show-up") in the same period.. Verified this using tags.. 
                - Also there are inconsistencies in AWS cost explorer output: when not applying the tag "test-delete-cost-explorer-show-up" the cost was $0.05 (for the m7a.medium instance only), but when applying the tag it was $0.06.....
    """
    total_cost = 0
    optimal_cost = 0 
    total_monthly_cost = 0
    optimal_monthly_cost = 0
    if multi_NIC: # i.e., if live ip rejuvenations
        # assert rej_count is not None, "rej_count must be provided for live ip rejuvenations"

        # Get optimal instance details: 
        optimal_instance_cost = instance_list[0]['optimal_cheapest_instance']['OptimalInstanceCost']
        optimal_instance_count = instance_list[0]['optimal_cheapest_instance']['OptimalInstanceCount']
        optimal_instance_nics = instance_list[0]['optimal_cheapest_instance']['OptimalInstanceMaxNICs']
        # Calculate optimal cost:
        optimal_nic_cost = 0.005 * int(optimal_instance_nics) / 60 * exp_duration * optimal_instance_count  # just the cost of the EIPs attached to it (statically) throughout the entire experiment
        optimal_instance_cost = float(optimal_instance_cost) / 60 * exp_duration * optimal_instance_count 
        optimal_cost = optimal_instance_cost + optimal_nic_cost

        # Iterate through each instance within instance_list: 
        for instance_details in instance_list:
            instance_cost = float(instance_details['InstanceCost']) / 60 * exp_duration # we assume that live IP is able to acquire the cheapest instance (this is reasonable since our exp will terminate if it weren't able to acquire the cheapest instance at initialization).
            # + float(instance_details['InstanceCost']) / 60 # instance charge is per-second granularity, but the first minute is also charged by default. 
            # Get the number of NICs of this instance_type:
            num_eips = len(instance_details['NICs'])
            # Calculate the cost of elastic IPs attached to this instance (assuming prior to Feb 1, where the ephemeral one is free..):
            # num_rejuvenations = math.ceil(exp_duration * 60 / rej_period)
            # num_rejuvenations = rej_count
            # per_rej_hours = math.ceil(rej_period/3600) # number of hours elapsed per rejuvenation
            nic_cost = 0.005 * num_eips / 60 * exp_duration # hour level granularity charge for allocated IP addresses
            # remapping_cost = num_eips * num_rejuvenations * 0.1 * 2 # only for AWS for now. Deallocate and allocate are both distinct operations that are remappings. 
            
            # Calculate total cost of NICs (skipping since additional ENIs are free..) + elastic IPs + instance_type + remapping cost:
            total_cost += instance_cost + nic_cost # + remapping_cost
    else:
        for instance_details in instance_list:
            instance_cost = float(instance_details['InstanceCost']) / 60 * exp_duration / rej_count # assume that each instance across all rejuvenation events has been running for an equal amount of time. 

            optimal_instance_cost = float(instance_details['optimal_cheapest_instance']['OptimalInstanceCost']) / 60 * exp_duration / rej_count # assume that each instance across all rejuvenation events has been running for an equal amount of time.

            eip_cost = 0.005 / 60 * exp_duration / rej_count

            # Calculate total cost of NICs (skipping since additional ENIs are free..) + elastic IPs + instance_type + remapping cost:
            total_cost += instance_cost + eip_cost
            optimal_cost += optimal_instance_cost + eip_cost

    total_monthly_cost = total_cost / exp_duration * 60 * 24 * 30
    optimal_monthly_cost = optimal_cost / exp_duration * 60 * 24 * 30

    return total_cost, optimal_cost, total_monthly_cost, optimal_monthly_cost

instance_list = [
    {
        "InstanceCost": 0.3731,
        "InstanceID": "i-04ae5313e8e0d98c6",
        "InstanceType": "r6a.4xlarge",
        "NICs": [
            [
                "eni-01d004c76bdb6eaf3",
                "eipalloc-00141c624e560ddcb",
                "eipassoc-0a2d10121af9c1aa4"
            ],
            [
                "eni-01070c962cce7456f",
                "eipalloc-0b372e34814b984d7",
                "eipassoc-0f4945303a2d2c063"
            ],
            [
                "eni-0421a37bc61c3fbc0",
                "eipalloc-0f91ab204f93e0a22",
                "eipassoc-0f831205ebeb1be3d"
            ],
            [
                "eni-04d46edd94e18f50a",
                "eipalloc-0a27847f6ebb0740a",
                "eipassoc-0125589349aad3613"
            ],
            [
                "eni-074288a3b8ad18d90",
                "eipalloc-0185c73d2855cc3a2",
                "eipassoc-05e855a76065c1009"
            ],
            [
                "eni-0034b7ca1564ffadb",
                "eipalloc-0b69c90d069535e68",
                "eipassoc-06ca0f0d2b80eba84"
            ],
            [
                "eni-07c3089d0d848313a",
                "eipalloc-0d5e27f384656c533",
                "eipassoc-0fda339db87de60db"
            ],
            [
                "eni-0efcf353bb17de3ac",
                "eipalloc-0fefa52732bcc7cbc",
                "eipassoc-0c0c062e08695c810"
            ]
        ],
        "ce_session_region": "us-east-1",
        "ec2_session_region": "us-east-1",
        "optimal_cheapest_instance": {
            "OptimalInstanceCost": 0.3731,
            "OptimalInstanceCount": 3,
            "OptimalInstanceMaxNICs": 8,
            "OptimalInstanceType": "r6a.4xlarge",
            "OptimalInstanceZone": "us-east-1b"
        }
    },
    {
        "InstanceCost": 0.3731,
        "InstanceID": "i-0a6926bb84a56cca6",
        "InstanceType": "r6a.4xlarge",
        "NICs": [
            [
                "eni-0961cd6a0fd95743d",
                "eipalloc-0f2e6cdf5c2d5fb9d",
                "eipassoc-0ae6c0a62d09c4ba6"
            ],
            [
                "eni-0bcfc1e0a478567d7",
                "eipalloc-0488ba29cbee9f850",
                "eipassoc-0ca9db7ad79169998"
            ],
            [
                "eni-02fa58ef7b229bbd6",
                "eipalloc-03c8c4aab4e4abddf",
                "eipassoc-05ec8b536de7bc460"
            ],
            [
                "eni-07f8571df9ea809d0",
                "eipalloc-048d9e27f4e44b0b6",
                "eipassoc-0905f7cc031465a89"
            ],
            [
                "eni-0b243c8dec503992a",
                "eipalloc-0692e2c7fdb0122ac",
                "eipassoc-08b75f426dd29d891"
            ],
            [
                "eni-0d4ac874f03456ca0",
                "eipalloc-021eeb174dbe0cad7",
                "eipassoc-0b9de2f7785d85923"
            ],
            [
                "eni-09ccbe6afd6845b83",
                "eipalloc-0c67b8f7fa13f391b",
                "eipassoc-0f1991c7df25c0d58"
            ],
            [
                "eni-054557624c866aaaa",
                "eipalloc-0451dfb292deec803",
                "eipassoc-084ee6bac1e2e667e"
            ]
        ],
        "ce_session_region": "us-east-1",
        "ec2_session_region": "us-east-1",
        "optimal_cheapest_instance": {
            "OptimalInstanceCost": 0.3731,
            "OptimalInstanceCount": 3,
            "OptimalInstanceMaxNICs": 8,
            "OptimalInstanceType": "r6a.4xlarge",
            "OptimalInstanceZone": "us-east-1b"
        }
    },
    {
        "InstanceCost": 0.3731,
        "InstanceID": "i-0168fd7a52afa2308",
        "InstanceType": "r6a.4xlarge",
        "NICs": [
            [
                "eni-002c2391a50c3ad39",
                "eipalloc-00f43526f804e8530",
                "eipassoc-0efef30ba98082318"
            ],
            [
                "eni-05fb59a1decd45c44",
                "eipalloc-07eb56a52420b35ff",
                "eipassoc-09ba92f055e8db192"
            ],
            [
                "eni-07697973b1e885d0b",
                "eipalloc-00e5eab5cf03d36c7",
                "eipassoc-0ca5fb1269b24f670"
            ],
            [
                "eni-095ab80782c23fe98",
                "eipalloc-05cec253325132b97",
                "eipassoc-07569e8389ba61d86"
            ],
            [
                "eni-013fccec6d33f15d3",
                "eipalloc-05d84da8a9fa3b4c0",
                "eipassoc-006d2c99e7cbe7710"
            ],
            [
                "eni-0dbab472c20b64115",
                "eipalloc-005cb3b531dcda90b",
                "eipassoc-046a62e9e3e59a7f5"
            ],
            [
                "eni-05a3f4e0f3bd70673",
                "eipalloc-0199f62311820bb43",
                "eipassoc-01d030f61180c074e"
            ],
            [
                "eni-02a62c98f16351b0b",
                "eipalloc-047da25b3712356b3",
                "eipassoc-0342fbe9b79e488bf"
            ]
        ],
        "ce_session_region": "us-east-1",
        "ec2_session_region": "us-east-1",
        "optimal_cheapest_instance": {
            "OptimalInstanceCost": 0.3731,
            "OptimalInstanceCount": 3,
            "OptimalInstanceMaxNICs": 8,
            "OptimalInstanceType": "r6a.4xlarge",
            "OptimalInstanceZone": "us-east-1b"
        }
    }
]

rej_period = 120
exp_duration = 10
multi_NIC = True

total_cost, optimal_cost, total_monthly_cost, optimal_monthly_cost = calculate_cost(instance_list, rej_period, exp_duration, multi_NIC=True, rej_count=None, ephemeral_charge=False)
print("Total cost: ", total_cost)
print("Optimal cost: ", optimal_cost)
print("Total monthly cost: ", total_monthly_cost)
print("Optimal monthly cost: ", optimal_monthly_cost)