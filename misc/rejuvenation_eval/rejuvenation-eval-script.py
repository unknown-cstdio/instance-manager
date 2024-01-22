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
import os
import math
import json
from collections import defaultdict
os.chdir("../..")
import api
os.chdir("misc/rejuvenation_eval")

def ping_instances(nic_list):
    """
        Checks if instances are pingable.

        Parameters:
            nic_list: list of NIC IDs
    """
    failed_ips = []
    for nic_details in nic_list:
        # ip = api.get_public_ip_address(ec2, nic_id)
        ip = nic_details[1]
        # ping the instance's ip:   
        # TODO: implement this
        # if ping fails, add to failed_ips
        failed_ips.append(ip)

    return failed_ips

def get_cheapest_instance_types_df(ec2, filter=None, multi_NIC=False):
    """
        Parameters:
            multi_NIC == True, used for liveIP and optimal 
            filter: price filter and region filter for now
                Format: {
                    "min_cost": float,
                    "max_cost": float,
                    "regions": ["us-east-1", ...], # list of regions to include in the creation process. Note: make sure a suitable launch template exists for each region listed
                    }

        df format:
        spot_prices.append({
            'AvailabilityZone': response['AvailabilityZone'],
            'InstanceType': response['InstanceType'],
            'MaximumNetworkInterfaces': type_to_NIC[response['InstanceType']],
            'SpotPrice': response['SpotPrice'],
            'PricePerInterface': (float(response['SpotPrice']) + 0.005 * (type_to_NIC[response['InstanceType']] - 1)) / type_to_NIC[response['InstanceType']],
            'Timestamp': response['Timestamp']  
        })

        returns the entire df sorted accordingly
    """

    # Look into cost catalogue and sort based on multi_NIC or not:
    prices = api.update_spot_prices(ec2) # AWS prices
    
    # Get sorted prices:
    if multi_NIC:
        prices = prices.sort_values(by=['PricePerInterface'], ascending=True)
    else:
        prices = prices.sort_values(by=['SpotPrice'], ascending=True)

    # Filter based on min_cost and max_cost, if filter exists:
    if isinstance(filter, dict):
        min_cost = filter['min_cost']
        max_cost = filter['max_cost']
        regions = filter['region']
        if regions:
            # Only keep rows where AvailabilityZone contains one of the values in the regions list:
            prices = prices[prices['AvailabilityZone'].str.startswith(tuple(regions))] # https://stackoverflow.com/a/20461857/13336187
        if min_cost:
            if multi_NIC:
                prices = prices[prices['PricePerInterface'] >= min_cost]
            else:
                prices = prices[prices['SpotPrice'] >= min_cost]
        if max_cost:
            if multi_NIC:
                prices = prices[prices['PricePerInterface'] <= max_cost]
            else:
                prices = prices[prices['SpotPrice'] <= max_cost]

    return prices

def create_fleet_live_ip_rejuvenation(ec2, prices, proxy_count, proxy_impl, tag):
    """
        Creates fleet combinations. 

        Parameters:
            - proxy_impl: "snowflake" | "wireguard" | "baseline"
    """
    # Get the cheapest instance now:
    instance_type_cost = prices.iloc[0]['PricePerInterface']
    instance_type = prices.iloc[0]['InstanceType']
    zone = prices.iloc[0]['AvailabilityZone']

    # Get the number of NICs in this instance type:
    max_nics = api.get_max_nics(ec2, instance_type)
    # Get number of instances needed:
    instances_to_create = math.ceil(proxy_count/max_nics)

    # Get suitable launch template based on the region associated with the zone:
    region = zone[:-1] # e.g., us-east-1a -> us-east-1
    launch_template = api.use_UM_launch_templates(ec2, region, proxy_impl)

    # Create the initial fleet with multiple NICs (with tag values as indicated above)
    response = api.create_fleet(ec2, instance_type, zone, launch_template, instances_to_create)
    # make sure that the required instances have been acquired: 
    instances = api.get_specific_instances_with_fleet_id_tag(response['fleet']) 
    if len(instances) != instances_to_create:
        raise Exception("Not enough instances were created: only created " + str(len(instances)) + " instances, but " + str(instances_to_create) + " were required.")

    print("Created {} instances of type {} with {} NICs each, and hourly cost {}".format(instances_to_create, instance_type, max_nics, instance_type_cost))

    instance_list = []

    for instance in instances:
        instance_details = {'InstanceID': instance, 'InstanceType': instance_type, 'NICs': []}
        # Create the NICs and associate them with the instances:
        nics = api.create_nics(ec2, instance, max_nics-1, tag)
        # Create the elastic IPs and associate them with the NICs:
        for nic in nics:
            eip = api.create_eip(ec2, nic, tag)
            instance_details['NICs'].append((nic, eip))
        instance_list.append(instance_details) 

    return instance_list
        
def create_fleet(ec2, proxy_count, proxy_impl, tag, filter=None, multi_NIC=False):
    """
        Creates the required fleet: 
        Parameters:
            filter: refer to get_cheapest_instance_types_df for definition 
            tag: will be used to tag all resources associated with this instance 
            multi_NIC == True, used for liveIP and optimal

        Returns:
            List of created instances (count guaranteed to be proxy_count)
                [
                    {
                        'InstanceID': instance_id,
                        'NICs': [(NIC ID, EIP ID), ...]
                    },
                    ...
                ]
    """
    if multi_NIC:
        prices = get_cheapest_instance_types_df(ec2, filter, multi_NIC=True)
        instance_list = create_fleet_live_ip_rejuvenation(ec2, prices, proxy_count, proxy_impl, tag) 
    else:
        prices = get_cheapest_instance_types_df(ec2, filter, multi_NIC=False)
        instance_list = create_fleet_instance_rejuvenation(ec2, prices, proxy_count, proxy_impl, tag)

    print("Create fleet success with details: ", json.dumps(instance_list, sort_keys=True, indent=4))
    return instance_list

def live_ip_rejuvenation(ec2, rej_period, proxy_count, exp_duration, filter=None, tag_prefix="liveip-expX-instance"):
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

    # Create initial fleet (with tag values as indicated above):
    instance_list = create_fleet(ec2, proxy_count, filter, tag, launch_template, multi_NIC=True)

    # Make sure instance can be sshed/pinged (fail rejuvenation if not):
    for instance_details in instance_list:
        failed_ips = ping_instances(instance_details['NICs'])
        assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)

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
    account_type = sys.argv[6]

    is_UM = account_type == 'UM'
    ec2, ce = choose_session(is_UM_AWS=is_UM, region=region)
    prices = update_spot_prices(ec2)
    prices = prices.sort_values(by=['SpotPrice'], ascending=True)
    print(prices.iloc[0])
    instance_type = prices.iloc[0]['InstanceType']
    zone = prices.iloc[0]['AvailabilityZone']
    current_type = instance_type
    launch_template = None
    if account_type == 'UM':
        launch_template_wireguard = "lt-077e7f82c173dd30a" # not working yet
        launch_template_baseline_working = "lt-07c37429821503fca"
        launch_template = launch_template_wireguard 
    else: # Basically, Jinyu account for now:
        launch_template = use_jinyu_launch_templates(ec2, instance_type)
        #use x86 launch template for now because proxy hasn't been compiled for arm yet, delete this in the future
        count = 0
        while launch_template != 'lt-04d9c8ac5d00a2078':
            count += 1
            instance_type = prices.iloc[count]['InstanceType']
            launch_template = use_jinyu_launch_templates(ec2, instance_type)
            zone = prices.iloc[count]['AvailabilityZone']
    print("using launch template: " + launch_template)
    
    response = create_fleet(ec2, instance_type, zone, launch_template, capacity)
    print(response)
    run(ec2)

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