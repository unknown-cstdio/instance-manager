"""
    Requirements:
        - Given our input (number of proxies, and filter), output the instance combinations required to satisfy this number of proxies.  
        - Other parameters:
            - Rejuvenation period
            - Experiment duration
        - A single experiment will be performed for all 3 bars (optimal, live IP and instance) simultaneously: for equal cost instance reasons
        - After applying the filter:
            - Live IP will choose the cheapest instance according to multi-NIC cost row
            - Instance will choose the cheapest instance according to single-NIC cost row (normal row)
        - Creating the instances: 
            - Live IP instances will be tagged with name "liveip-expX-instanceY" where Y is the number ID, create a network interface and allocate/associate a new elastic IP to it, and assign the NIC to the instances. Do this for ALL NICs, even the ephemeral IP one. 
            - Instance rejuvenation instances will be tagged with name "instance-expX-instanceY" where Y is the number ID
            - Optimal instances will be tagged with name "optimal-expX-instanceY" where Y is the number ID
        - Rejuvenation algorithm (i.e., replacing the instances)
            - Live IP: when rejuvenation period is reached, deallocate all elastic IPs on the NICs, and allocate/associate new elastic IPs to them. 
            - Instance: when rejuvenation period is reached, create a new instance, once the instance is successfully instantiated (i.e., can ssh into it), we terminate the previous instance. If the time it takes to instantiate exceeds the rejuvenation period, we consider this an unsuccessful rejuvenation, and we repeat the experiment with a higher rejuvenation period
        - Helper functions in api.py (that Pat doesn't think we have now):
            - be able to retrieve existing instances and change their name
            - be able to do cost allocation name tags
            - be able to create new NICs, and associate/disassociate elastic IPs to them
            - be able to associate NICs to instances
            - be able to check if instances have been successfully instantiated (i.e., passed all checks?), and be able to ssh into them (as a secondary test)
        - Functionalities required by AWS:
            - Cost explorer should be able to retrieve tag values that no longer exist currently (e.g., instances that have been removed..)
            - elastic IP cost associated with only the specific instances should be filter-able/viewable.. s
"""

import time 

def get_cheapest_instance_types_df(multi_NIC=False):
    """
        multi_NIC == True, used for liveIP and optimal 
    """
    # Look into cost catalogue and sort based on multi_NIC or not:

    # Get first row:

    return 

def live_ip_rejuvenation(rej_period, proxy_count, exp_duration, tag_prefix="liveip-expX-instance"):
    """
        Runs in a loop. 

        Parameters:
            rej_period: in seconds
            exp_duration: in minutes 

        Returns: cost of this experiment
    """
    t_end = time.time() + 60 * exp_duration

    tag_suffix = 1
    tag = tag_prefix + str(tag_suffix)

    # Get the cheapest instance now:
    instance_type, instance_type_cost = get_cheapest_instance_types_df(multi_NIC=True)
    
    # Create the initial fleet with multiple NICs (with tag values as indicated above)
    
    # Allocate and associate elastic IPs to all of the NICs (including original one) (with tag values as indicated above):

    # Make sure instance can be sshed/pinged (fail rejuvenation if not):

    # Sleep for rej_period:
    time.sleep(rej_period)

    # Continue with rejuvenation:
    while time.time() < t_end:
        tag = tag_prefix + str(tag_suffix)

        # Deassociate and deallocate NICs from instances (including original one) (with tag values as indicated above):
        
        # Allocate and associate elastic IPs to all of the NICs (including original one) (with tag values as indicated above):

        # Sleep for rej_period:
        time.sleep(rej_period)
    
    return calculate_cost(instance_type, instance_type_cost, exp_duration, multi_NIC=True)

def instance_rejuvenation(rej_period, proxy_count, exp_duration, tag_prefix="instance-expX-instance"):
    """
        Runs in a loop. 

        Parameters:
            rej_period: in seconds
            exp_duration: in minutes 

        Returns: cost of this experiment
    """
    

    return 

def calculate_cost(instance_type, instance_type_cost, exp_duration, multi_NIC=True):
    """
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

    if multi_NIC:
        # Get the number of NICs of this instance_type:

        # Calculate the cost of NICs + elastic IPs attached to this instance (assuming prior to Feb 1, where the ephemeral one is free..):
        cost = 0 

    # Calculate total cost of NICs + elastic IPs + instance_type 


    return cost 


if __name__ == '__main__':
    REJUVENATION_PERIOD = sys.argv[1] # in seconds
    EXPERIMENT_DURATION = sys.argv[2] # in minutes
    PROXY_COUNT = sys.argv[3] # aka fleet size 
    MIN_VCPU = sys.argv[4]
    MAX_VCPU = sys.argv[5]

    region = sys.argv[2][:-1]
    num = int(sys.argv[3])
    prices = update_spot_prices()
    prices.sort_values(by=['SpotPrice'])
    instance_type = prices.iloc[0]['InstanceType']
    availability_zone = prices.iloc[0]['AvailabilityZone']
    availability_zone = sys.argv[2] # not doing cheapest allocation yet, since we are overriding this with a user provided az (e.g., us-east-1a) instead
    if account_type == 'UM':
        ec2, ce = choose_session(is_UM_AWS=True, region=region)
        launch_template_wireguard = "lt-077e7f82c173dd30a" # not working yet
        launch_template_baseline_working = "lt-07c37429821503fca"
        launch_template = launch_template_wireguard 
    else: # Basically, Jinyu account for now:
        ec2, ce = choose_session(is_UM_AWS=False, region=region)
        instances = get_all_instances()
        #clean up existing instances. (This is dangerous for UM, because our instance-manager or controllers will be deleted too!)
        for instance in instances:
            if instance != INSTANCE_MANAGER_INSTANCE_ID: # do not delete our UM instance-manager/controller
                response = terminate_instances([instance])
        launch_template = use_jinyu_launch_templates(instance_type)
    
    response = create_fleet(instance_type, availability_zone, launch_template, num)
    print(response)
    run()

    # Some example usage from Patrick:
    """
    response = get_all_instances()

    # Create two instances: 
    UM_launch_template_id = "lt-07c37429821503fca"
    response = create_fleet("t2.micro", "us-east-1c", UM_launch_template_id, 2) # verified working (USE THIS)

    response = create_fleet2("t2.micro", "us-east-1c", UM_launch_template_id, 2) # not working yet

    print(response)

    # Delete instances using the fleet-id key returned from the response above:

    instance_ids = get_specific_instances_with_fleet_id_tag('fleet-4da19c85-1000-4883-a480-c0b7a34b444b')
    print(instance_ids)
    for i in instance_ids:
        response = terminate_instances([i])
        print(response)
    """