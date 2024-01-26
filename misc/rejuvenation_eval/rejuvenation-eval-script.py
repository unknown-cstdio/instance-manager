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
import sys, os
import math
import json
import warnings
from collections import defaultdict
sys.path.append("../../")
import api

def pretty_json(obj):
    return json.dumps(obj, sort_keys=True, indent=4, default=str)

def print_stdout_and_filename(string, filename):
    print(string)
    with open(filename, 'a') as file:
        file.write(string + "\n")

def chunks(lst, n):
    """
        Breaks a list into equally sized chunks of size n.
        Parameters:
            lst: list
            n: int

        https://stackoverflow.com/a/312464/13336187

        Usage example: list(chunks(range(10, 75), 10)
    """
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def ping_instances(ec2, nic_list, multi_NIC=True, not_fixed=True):
    """
        Checks if instances are pingable.

        Parameters:
            nic_list: list of NIC IDs
            not_fixed: True | False
                - True: # TODO Minor quirk that will be removed later: only the default NIC (i.e., original_nic) is configured to accept pings for now. We will need to fix this later. Will remove this parameter altogether once fixed. 
    """
    failed_ips = []
    # time.sleep(wait_time)
    if not_fixed: # only ping the original NIC
        nic_details = nic_list[-1] # this is the position of the original_nic, since we append it last..
        if multi_NIC:
            ip = api.get_public_ip_address(ec2, nic_details[1])
        else:
            ip = nic_details[1]
        response = os.system("ping -c 1 " + ip)
        if response == 0:
            print(f"{ip} is up!")
        else:
            print(f"{ip} is down!")
            # if ping fails, add to failed_ips
            failed_ips.append(ip)
    else: # ping all NICs
        for nic_details in nic_list:
            if multi_NIC:
                ip = api.get_public_ip_address(ec2, nic_details[1])
            else:
                ip = nic_details[1]
            response = os.system("ping -c 1 " + ip)
            if response == 0:
                print(f"{ip} is up!")
            else:
                print(f"{ip} is down!")
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
        regions = filter['regions']
        if regions:
            # Only keep rows where AvailabilityZone contains one of the values in the regions list:
            prices = prices[prices['AvailabilityZone'].str.startswith(tuple(regions))] # https://stackoverflow.com/a/20461857/13336187
        if min_cost:
            if multi_NIC:
                prices = prices[prices['PricePerInterface'] >= min_cost]
            else:
                # print(prices.dtypes)
                # print(isinstance(prices['PricePerInterface'], float))
                # print(isinstance(min_cost, float))
                prices = prices[prices['SpotPrice'] >= min_cost]
        if max_cost:
            if multi_NIC:
                prices = prices[prices['PricePerInterface'] <= max_cost]
            else:
                prices = prices[prices['SpotPrice'] <= max_cost]

    return prices

def get_instance_row_with_supported_architecture(ec2, prices, supported_architecture=['x86_64']):
    """
        Parameters:
            supported_architecture: list of architectures to support. Default is x86_64 (i.e., Intel/AMD)
            prices: df of prices (from get_cheapest_instance_types_df)
        Returns:
            row of the cheapest instance type that supports the architecture
    """
    for index, row in prices.iterrows():
        instance_type = row['InstanceType']
        instance_info = api.get_instance_type(ec2, [instance_type])
        if instance_info['InstanceTypes'][0]['ProcessorInfo']['SupportedArchitectures'][0] in supported_architecture:
            return index, row
    raise Exception("No instance type supports the architecture: " + str(supported_architecture))

def create_fleet_live_ip_rejuvenation(ec2, cheapest_instance, proxy_count, proxy_impl, tag_prefix, wait_time_after_create=15, print_filename="data/output-general.txt"):
    """
        Creates fleet combinations. 

        Parameters:
            - cheapest_instance: row of the cheapest instance type (from get_cheapest_instance_types_df)
            - proxy_impl: "snowflake" | "wireguard" | "baseline"
            - tag_prefix: "liveip-expX" 
            - wait_time_after_create: in seconds
    """
    # Get the cheapest instance now:
    instance_type_cost = cheapest_instance['SpotPrice']
    instance_type = cheapest_instance['InstanceType']
    zone = cheapest_instance['AvailabilityZone']
    region = zone[:-1] # e.g., us-east-1a -> us-east-1

    # Get the number of NICs in this instance type:
    max_nics = api.get_max_nics(ec2, instance_type)
    # Get number of instances needed:
    instances_to_create = math.ceil(proxy_count/max_nics)

    # Get suitable launch template based on the region associated with the zone:
    launch_template = api.use_UM_launch_templates(ec2, region, proxy_impl, "main")

    # Create the initial fleet with multiple NICs (with tag values as indicated above)
    response = api.create_fleet(ec2, instance_type, zone, launch_template, instances_to_create)
    time.sleep(wait_time_after_create) # wait awhile for fleet to be created
    # make sure that the required instances have been acquired: 
    print(response['FleetId'])
    print(pretty_json(response))
    all_instance_details = api.get_specific_instances_with_fleet_id_tag(ec2, response['FleetId'], "raw") 
    if len(all_instance_details) != instances_to_create:
        raise Exception("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(instances_to_create) + " were required.")

    # print("Created {} instances of type {} with {} NICs each, and hourly cost {}".format(instances_to_create, instance_type, max_nics, instance_type_cost))
    print_stdout_and_filename("Created {} instances of type {} with {} NICs each, and hourly cost {}".format(instances_to_create, instance_type, max_nics, instance_type_cost), print_filename)

    instance_list = []

    for index, original_instance_details in enumerate(all_instance_details):
        instance = original_instance_details['InstanceId']
        # Tag created instance:
        instance_tag = tag_prefix + "-instance{}".format(str(index))
        api.assign_name_tags(ec2, instance, instance_tag) 
        
        instance_details = {'InstanceID': instance, 'InstanceCost': instance_type_cost, 'InstanceType': instance_type, 'NICs': []}
        # Get original NIC attached to the instance:
        original_nic = original_instance_details['NetworkInterfaces'][0]['NetworkInterfaceId']
        assert len(original_instance_details['NetworkInterfaces']) == 1, "Expected only 1 NIC, but got " + str(len(original_instance_details['NetworkInterfaces']))
        # _ , original_nic = api.get_specific_instances_attached_components(ec2, instance)

        # Create the NICs and associate them with the instances:
        nics = api.create_nics(ec2, instance, max_nics-1, zone)

        nics.append(original_nic)
        # Create the elastic IPs and associate them with the NICs:
        for index2, nic in enumerate(nics):
            # eip = api.create_eip(ec2, nic, tag)
            eip = api.get_eip_id_from_allocation_response(api.allocate_address(ec2))
            # print(api.associate_address(ec2, instance, eip, nic))
            assoc_id = api.get_association_id_from_association_response(api.associate_address(ec2, instance, eip, nic))
            instance_details['NICs'].append((nic, eip, assoc_id))

            # Tag NICs and EIPs:
            nic_tag = instance_tag + "-nic{}".format(str(index2))
            eip_tag = nic_tag + "-eip{}".format(str(index2))
            api.assign_name_tags(ec2, nic, nic_tag)
            api.assign_name_tags(ec2, eip, eip_tag)

        instance_list.append(instance_details) 

    return instance_list

def create_fleet_instance_rejuvenation(ec2, cheapest_instance, proxy_count, proxy_impl, tag_prefix, wait_time_after_create=15, print_filename="data/output-general.txt"):
    """
        Creates fleet combinations. 

        Parameters:
            - cheapest_instance: row of the cheapest instance type (from get_cheapest_instance_types_df)
            - proxy_impl: "snowflake" | "wireguard" | "baseline"
            - tag_prefix: "instance-expX" 
            - wait_time_after_create: in seconds
    """
    proxy_count_remaining = proxy_count

    # Get the cheapest instance now:
    instance_type_cost = cheapest_instance['SpotPrice']
    instance_type = cheapest_instance['InstanceType']
    zone = cheapest_instance['AvailabilityZone']
    region = zone[:-1] # e.g., us-east-1a -> us-east-1

    # Get suitable launch template based on the region associated with the zone:
    launch_template = api.use_UM_launch_templates(ec2, region, proxy_impl, "main")

    # Create the initial fleet with multiple NICs (with tag values as indicated above)
    response = api.create_fleet(ec2, instance_type, zone, launch_template, proxy_count)
    time.sleep(wait_time_after_create) # wait awhile for fleet to be created
    # make sure that the required instances have been acquired: 
    print(response['FleetId'])
    all_instance_details = api.get_specific_instances_with_fleet_id_tag(ec2, response['FleetId'], "raw") 
    if len(all_instance_details) != proxy_count:
        warnings.warn("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(proxy_count) + " were required.")
        print_stdout_and_filename("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(proxy_count) + " were required.", print_filename)
    proxy_count_remaining = proxy_count - len(all_instance_details)

    # print("Created {} instances of type {}, and hourly cost {}. Remaining instances to create: {}".format(len(all_instance_details), instance_type, instance_type_cost, proxy_count_remaining))
    print_stdout_and_filename("Created {} instances of type {}, and hourly cost {}. Remaining instances to create: {}".format(len(all_instance_details), instance_type, instance_type_cost, proxy_count_remaining), print_filename)

    instance_list = []

    for index, original_instance_details in enumerate(all_instance_details):
        instance = original_instance_details['InstanceId']
        # Tag created instance:
        instance_tag = tag_prefix + "-instance{}".format(str(index))
        api.assign_name_tags(ec2, instance, instance_tag) 
        
        instance_details = {'InstanceID': instance, 'InstanceCost': instance_type_cost, 'InstanceType': instance_type, 'NICs': []}
        # Get original NIC attached to the instance:
        original_nic = original_instance_details['NetworkInterfaces'][0]['NetworkInterfaceId']
        original_pub_ip = original_instance_details['PublicIpAddress']
        assert len(original_instance_details['NetworkInterfaces']) == 1, "Expected only 1 NIC, but got " + str(len(original_instance_details['NetworkInterfaces']))
        # _ , original_nic = api.get_specific_instances_attached_components(ec2, instance)

        # Tag the original NIC:
        instance_details['NICs'] = [(original_nic, original_pub_ip)]
        nic_tag = instance_tag + "-nic{}".format(str(1))
        api.assign_name_tags(ec2, original_nic, nic_tag)

        instance_list.append(instance_details) 

    return instance_list, proxy_count_remaining
        
def create_fleet(initial_ec2, is_UM, proxy_count, proxy_impl, tag_prefix, filter=None, multi_NIC=False, wait_time_after_create=15, print_filename="data/output-general.txt"):
    """
        Creates the required fleet: 
        Parameters:
            filter: refer to get_cheapest_instance_types_df for definition 
            tag_prefix: will be used to tag all resources associated with this instance 
            multi_NIC == True, used for liveIP and optimal
            wait_time_after_create: in seconds

        Returns:
            List of created instances (count guaranteed to be proxy_count)
                [
                    {
                        'InstanceID': instance_id,
                        'InstanceType': instance_type,
                        'InstanceCost': float,
                        'NICs': [(NIC ID, EIP ID, ASSOCIATION ID), ...]
                    },
                    ...
                ]

            Note, for instance rejuvenation, the list is slightly different:
                [
                        {
                            'InstanceID': instance_id,
                            'InstanceType': instance_type,
                            'InstanceCost': float,
                            'ec2_session': <ec2-session-object>,
                            'ce_session': <ce-session-object>,
                            'NICs': [(NIC ID, EIP ID, ASSOCIATION ID), ...]
                        },
                        ...
                ]
    """
    if multi_NIC:
        prices = get_cheapest_instance_types_df(initial_ec2, filter, multi_NIC=True)
        _ , cheapest_instance = get_instance_row_with_supported_architecture(initial_ec2, prices)
        # cheapest_instance = prices.iloc[0]
        cheapest_instance_region = cheapest_instance['AvailabilityZone'][:-1]
        # NOTE: by assigning a session here directly, we are assuming that the instance will be created successfully and completely with only this cheapest_instance that is in this region. We can expand this in future with little code modifications. 
        ec2, ce = api.choose_session(is_UM_AWS=is_UM, region=cheapest_instance_region)
        instance_list = create_fleet_live_ip_rejuvenation(ec2, cheapest_instance, proxy_count, proxy_impl, tag_prefix, wait_time_after_create, print_filename=print_filename) # expected tag_prefix: "liveip-expX" where X is the user-provided experiment number
        # print("Create fleet success with details: ", pretty_json(instance_list))
        print_stdout_and_filename("Create fleet success with details: " + pretty_json(instance_list), print_filename)
        return instance_list, ec2, ce
    else:
        prices = get_cheapest_instance_types_df(initial_ec2, filter, multi_NIC=False)
        instance_list = loop_create_fleet_instance_rejuvenation(initial_ec2, is_UM, prices, proxy_count, proxy_impl, tag_prefix, wait_time_after_create, print_filename=print_filename)
        # print("Create fleet success with details: ", pretty_json(instance_list))
        print_stdout_and_filename("Create fleet success with details: " + pretty_json(instance_list), print_filename)
        return instance_list

def loop_create_fleet_instance_rejuvenation(initial_ec2, is_UM, prices, proxy_count, proxy_impl, tag_prefix, wait_time_after_create=15, print_filename="data/output-general.txt"):
    proxy_count_remaining = proxy_count
    instance_list = []
    ec2_list = []
    ce_list = []
    print_stdout_and_filename("Original number of rows in prices dataframe: " + str(len(prices.index)), print_filename)
    # df.to_string(header=False, index=False)
    print_stdout_and_filename(prices.to_string(), print_filename) # https://stackoverflow.com/a/58070237/13336187
    count = 1
    prices = prices.reset_index(drop=True) # reset index. https://stackoverflow.com/a/20491748/13336187
    while proxy_count_remaining > 0:
        index, cheapest_instance = get_instance_row_with_supported_architecture(initial_ec2, prices)
        prices = prices[index+1:] # if we repeat this loop, it means that we were not able to create enough instances of this type (i.e., index), so we should search from there onwards.
        print_stdout_and_filename("Iteration {}: Number of rows in prices dataframe: ".format(count) + str(len(prices.index)), print_filename)
        # df.to_string(header=False, index=False)
        print_stdout_and_filename(prices.to_string(), print_filename) # https://stackoverflow.com/a/58070237/13336187
        cheapest_instance_region = cheapest_instance['AvailabilityZone'][:-1]
        ec2, ce = api.choose_session(is_UM_AWS=is_UM, region=cheapest_instance_region)
        instance_list_now, proxy_count_remaining = create_fleet_instance_rejuvenation(ec2, cheapest_instance, proxy_count_remaining, proxy_impl, tag_prefix, wait_time_after_create, print_filename=print_filename)
        for ins in instance_list_now:
            ins['ec2_session'] = ec2
            ins['ce_session'] = ce
        # ec2_list.extend([ec2 for i in range(len(instance_list_now))]) # each instance will have its own ec2 session (in case this is different across instances...)
        # ce_list.extend([ce for i in range(len(instance_list_now))]) # each instance will have its own ce session (in case this is different across instances...)
        instance_list.extend(instance_list_now)
        count += 1

    return instance_list


def live_ip_rejuvenation(initial_ec2, is_UM, rej_period, proxy_count, exp_duration, proxy_impl, filter=None, tag_prefix="liveip-expX", wait_time_after_create=15, wait_time_after_nic=30, print_filename="data/output-general.txt"):
    """
        Runs in a loop. 

        Parameters:
            rej_period: in seconds
            exp_duration: in minutes 
            proxy_impl = "wireguard"
            tag_prefix = "liveip-exp" + str(INITIAL_EXPERIMENT_INDEX)
            filter = {
                "min_cost": 0.002,
                "max_cost": 0.3,
                "regions": ["us-east-1"]
            }
            wait_time_after_create: in seconds
            wait_time_after_nic: in seconds
                - Time to wait before pinging the instance. This is to allow the instance to be fully instantiated before pinging it.

        Returns: cost of this experiment
    """
    t_end = time.time() + 60 * exp_duration

    print_stdout_and_filename("Begin Rejuvenation count: " + str(1), print_filename)

    # Create initial fleet (with tag values as indicated above):
    instance_list, ec2, ce = create_fleet(initial_ec2, is_UM, proxy_count, proxy_impl, tag_prefix, filter=filter, multi_NIC=True, wait_time_after_create=wait_time_after_create, print_filename=print_filename)

    # Make sure instance can be sshed/pinged (fail rejuvenation if not):
    time.sleep(wait_time_after_nic)
    for instance_details in instance_list:
        failed_ips = ping_instances(ec2, instance_details['NICs'], multi_NIC=True)
        if len(failed_ips) != 0:
            print_stdout_and_filename("Failed to ssh/ping into instances: " + str(failed_ips), print_filename)
            raise Exception("Failed to ssh/ping into instances: " + str(failed_ips))
        # assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)

    # Sleep for rej_period:
    time.sleep(rej_period)

    # Continue with rejuvenation:
    rejuvenation_index = 2
    while time.time() < t_end:
        print_stdout_and_filename("Begin Rejuvenation count: " + str(rejuvenation_index), print_filename)
        for index, instance_details in enumerate(instance_list): 
            instance_tag = tag_prefix + "-instance{}".format(str(index))
            instance = instance_details['InstanceID']
            new_nic_details = []
            for index2, nic_details in enumerate(instance_details['NICs']):
                 # Deassociate and deallocate NICs from instances (including original one) (with tag values as indicated above):
                api.disassociate_address(ec2, nic_details[2])
                api.release_address(ec2, nic_details[1])

                nic = nic_details[0]

                # Allocate and associate elastic IPs to all of the NICs (including original one) (with tag values as indicated above):
                # eip = api.create_eip(ec2, nic, tag)
                eip = api.get_eip_id_from_allocation_response(api.allocate_address(ec2))
                # api.associate_address(ec2, instance, eip, nic)
                assoc_id = api.get_association_id_from_association_response(api.associate_address(ec2, instance, eip, nic))
                new_nic_details.append((nic, eip, assoc_id))

                # Tag NICs and EIPs:
                nic_tag = instance_tag + "-nic{}".format(str(index2))
                eip_tag = nic_tag + "-eip{}".format(str(index2))
                api.assign_name_tags(ec2, nic, nic_tag)
                api.assign_name_tags(ec2, eip, eip_tag)
            instance_details['NICs'] = new_nic_details
    
        # Make sure instance can be sshed/pinged (fail rejuvenation if not):
        time.sleep(wait_time_after_nic)
        for instance_details in instance_list:
            failed_ips = ping_instances(ec2, instance_details['NICs'], multi_NIC=True)
            if len(failed_ips) != 0:
                with open(print_filename, 'a') as file:
                    print_stdout_and_filename("Failed to ssh/ping into instances: " + str(failed_ips), print_filename)
                    assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)

        # Print new details:
        # print("Concluded Rejuvenation count: ", rejuvenation_index)
        print_stdout_and_filename("Concluded Rejuvenation count: " + str(rejuvenation_index), print_filename)
        # print("New instance details: ", pretty_json(instance_list))
        print_stdout_and_filename("New instance details: " + pretty_json(instance_list), print_filename)
        rejuvenation_index += 1

        # Sleep for rej_period:
        time.sleep(rej_period)

    # Get total cost:
    total_cost = calculate_cost(instance_list, rej_period, exp_duration, multi_NIC=True, rej_count=rejuvenation_index-1)
    # print("Total cost of this live IP rejuvenation experiment: {}".format(total_cost))
    print_stdout_and_filename("Total cost of this live IP rejuvenation experiment: {}".format(total_cost), print_filename)

    # Remove instances (and NICs) and EIPs:
    for instance_details in instance_list:
        for nic_details in instance_details['NICs']:
            api.disassociate_address(ec2, nic_details[2])
            api.release_address(ec2, nic_details[1])
        instance = instance_details['InstanceID']
        api.terminate_instances(ec2, [instance])
    
    return 

def instance_rejuvenation(initial_ec2, is_UM, rej_period, proxy_count, exp_duration, proxy_impl, filter=None, tag_prefix="instance-expX", wait_time_after_create=15, wait_time_after_nic=30, print_filename="data/output-general.txt"):
    """
        Runs in a loop. 

        Parameters:
            rej_period: in seconds
            exp_duration: in minutes 
            wait_time_after_create: in seconds
            wait_time_after_nic: in seconds
                - Time to wait before pinging the instance. This is to allow the instance to be fully instantiated before pinging it.

        Returns: cost of this experiment
    """

    t_end = time.time() + 60 * exp_duration

    instance_lists = []

    print_stdout_and_filename("Begin Rejuvenation count: " + str(1), print_filename)

    # Create fleet (with tag values as indicated above):
    instance_list_prev = create_fleet(initial_ec2, is_UM, proxy_count, proxy_impl, tag_prefix, filter=filter, multi_NIC=False, wait_time_after_create=wait_time_after_create, print_filename=print_filename)
    instance_lists.extend(instance_list_prev)
    # Make sure instance can be sshed/pinged (fail rejuvenation if not):
    time.sleep(wait_time_after_nic)
    for index, instance_details in enumerate(instance_list_prev):
        failed_ips = ping_instances(instance_details['ec2_session'], instance_details['NICs'], multi_NIC=False)
        if len(failed_ips) != 0:
            print_stdout_and_filename("Failed to ssh/ping into instances: " + str(failed_ips), print_filename)
            assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)

    # Continue with rejuvenation:
    rejuvenation_index = 2
    while time.time() < t_end:
        # print("Begin Rejuvenation count: ", rejuvenation_index)
        print_stdout_and_filename("Begin Rejuvenation count: " + str(rejuvenation_index), print_filename)

        # Create fleet (with tag values as indicated above):
        instance_list = create_fleet(initial_ec2, is_UM, proxy_count, proxy_impl, tag_prefix, filter=filter, multi_NIC=False, wait_time_after_create=wait_time_after_create, print_filename=print_filename)

        # Make sure instance can be sshed/pinged (fail rejuvenation if not):
        time.sleep(wait_time_after_nic)
        for index, instance_details in enumerate(instance_list):
            failed_ips = ping_instances(instance_details['ec2_session'], instance_details['NICs'], multi_NIC=False)
            if len(failed_ips) != 0:
                print_stdout_and_filename("Failed to ssh/ping into instances: " + str(failed_ips), print_filename)
                assert len(failed_ips) == 0, "Failed to ssh/ping into instances: " + str(failed_ips)

        # Terminate fleet:
        # Chunk list into groups of 100: Maybe work on this next time..
        # chunk_terminate_instances(instance_list_prev, 100)
        # def chunk_terminate_instances(instance_list, chunk_size):
        #     for index, chunk in enumerate(list(chunks(instance_list, chunk_size))):
        #         instance_ids = [instance_details['InstanceID'] for instance_details in chunk]
        #         for ec2 in ec2_list:
        #             api.terminate_instances(ec2, instance_ids)
        for index, instance_details in enumerate(instance_list_prev):
            instance = instance_details['InstanceID']
            api.terminate_instances(instance_details['ec2_session'], [instance])

        # To be terminated in next rejuvenation:
        instance_list_prev = instance_list
        instance_lists.extend(instance_list_prev)
        
        # Sleep for rej_period:
        time.sleep(rej_period)

        # Print new details:
        # print("Concluded Rejuvenation count: ", rejuvenation_index)
        print_stdout_and_filename("Concluded Rejuvenation count: " + str(rejuvenation_index), print_filename)
        # print("New instance details: ", pretty_json(instance_list))
        print_stdout_and_filename("New instance details: " + pretty_json(instance_list), print_filename)
        rejuvenation_index += 1
    
    # Terminate remaining instances:
    for index, instance_details in enumerate(instance_list_prev):
        instance = instance_details['InstanceID']
        api.terminate_instances(instance_details['ec2_session'], [instance])
    
    # Get total cost:
    total_cost = calculate_cost(instance_lists, rej_period, exp_duration, multi_NIC=False)
    print_stdout_and_filename("Total cost of this instance rejuvenation experiment: {}".format(total_cost), print_filename)
    # print("Total cost of this instance rejuvenation experiment: {}".format())

    return 

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
    if multi_NIC: # i.e., if live ip rejuvenations
        assert rej_count is not None, "rej_count must be provided for live ip rejuvenations"
        # Iterate through each instance within instance_list: 
        for instance_details in instance_list:
            instance_cost = float(instance_details['InstanceCost']) / 60 * exp_duration 
            # + float(instance_details['InstanceCost']) / 60 # instance charge is per-second granularity, but the first minute is also charged by default. 
            # Get the number of NICs of this instance_type:
            num_eips = len(instance_details['NICs'])
            # Calculate the cost of elastic IPs attached to this instance (assuming prior to Feb 1, where the ephemeral one is free..):
            # num_rejuvenations = math.ceil(exp_duration * 60 / rej_period)
            num_rejuvenations = rej_count
            per_rej_hours = math.ceil(rej_period/3600) # number of hours elapsed per rejuvenation
            nic_cost = 0.005 * num_eips * num_rejuvenations * per_rej_hours # hour level granularity charge for allocated IP addresses
            remapping_cost = num_eips * num_rejuvenations * 0.1 * 2 # only for AWS for now. Deallocate and allocate are both distinct operations that are remappings. 

            # Calculate total cost of NICs (skipping since additional ENIs are free..) + elastic IPs + instance_type + remapping cost:
            total_cost += instance_cost + nic_cost + remapping_cost
    else:
        for instance_details in instance_list:
            instance_cost = float(instance_details['InstanceCost']) / 60 * exp_duration 

            # Calculate total cost of NICs (skipping since additional ENIs are free..) + elastic IPs + instance_type + remapping cost:
            total_cost += instance_cost

    return total_cost 

# Usage example: python3 rejuvenation-eval-script.py 20 2 1 2 1 2 wireguard UM all
if __name__ == '__main__':
    REJUVENATION_PERIOD = int(sys.argv[1]) # in seconds
    EXPERIMENT_DURATION = int(sys.argv[2]) # in minutes
    INITIAL_EXPERIMENT_INDEX = int(sys.argv[3])
    PROXY_COUNT = int(sys.argv[4]) # aka fleet size 
    MIN_VCPU = int(sys.argv[5]) # not used for now
    MAX_VCPU = int(sys.argv[6]) # not used for now
    PROXY_IMPL = sys.argv[7] # wireguard | snowflake | baseline
    account_type = sys.argv[8] # UM | anything else
    mode = sys.argv[9] # liveip | instance | all

    is_UM = account_type == 'UM'

    initial_ec2, initial_ce = api.choose_session(is_UM_AWS=is_UM, region='us-east-1') # used for whatever is needed. but may not be the same as that used for creating the instance fleet, as that depends on the region of the instance type.

    # Convenient way to nuke everything (for debugging only, uncomment to use... Need to move this elsewhere later):
    # api.nuke_all_instances(initial_ec2, ['i-035f88ca820e399e7'])
    # print("NUKED EVERYTING")
    # while True:
    #     X=1
    
    filter = {
        "min_cost": 0.05, #0.002 for first round of exps..
        "max_cost": 0.3,
        "regions": ["us-east-1"]
    }
    wait_time_after_create = 30
    # try: 
    if mode == "instance":
        tag_prefix = "instance-exp{}-{}fleet-{}mincost".format(str(INITIAL_EXPERIMENT_INDEX), str(PROXY_COUNT), str(filter['min_cost']))
        filename = "data/" + tag_prefix + ".txt"
        file = open(filename, 'w+')
        instance_rejuvenation(initial_ec2, is_UM, REJUVENATION_PERIOD, PROXY_COUNT, EXPERIMENT_DURATION, PROXY_IMPL, filter=filter, tag_prefix=tag_prefix, wait_time_after_create=wait_time_after_create, print_filename=filename)
    elif mode == "liveip":
        tag_prefix = "liveip-exp{}-{}fleet-{}mincost".format(str(INITIAL_EXPERIMENT_INDEX), str(PROXY_COUNT), str(filter['min_cost']))
        filename = "data/" + tag_prefix + ".txt"
        file = open(filename, 'w+')
        live_ip_rejuvenation(initial_ec2, is_UM, REJUVENATION_PERIOD, PROXY_COUNT, EXPERIMENT_DURATION, PROXY_IMPL, filter=filter, tag_prefix=tag_prefix, wait_time_after_create=wait_time_after_create, print_filename=filename)
    elif mode == "all":
        tag_prefix = "instance-exp{}-{}fleet-{}mincost".format(str(INITIAL_EXPERIMENT_INDEX), str(PROXY_COUNT), str(filter['min_cost']))
        filename = "data/" + tag_prefix + ".txt"
        file = open(filename, 'w+')
        instance_rejuvenation(initial_ec2, is_UM, REJUVENATION_PERIOD, PROXY_COUNT, EXPERIMENT_DURATION, PROXY_IMPL, filter=filter, tag_prefix=tag_prefix, wait_time_after_create=wait_time_after_create, print_filename=filename)
        tag_prefix = "liveip-exp{}-{}fleet-{}mincost".format(str(INITIAL_EXPERIMENT_INDEX), str(PROXY_COUNT), str(filter['min_cost']))
        filename = "data/" + tag_prefix + ".txt"
        file = open(filename, 'w+')
        live_ip_rejuvenation(initial_ec2, is_UM, REJUVENATION_PERIOD, PROXY_COUNT, EXPERIMENT_DURATION, PROXY_IMPL, filter=filter, tag_prefix=tag_prefix, wait_time_after_create=wait_time_after_create, print_filename=filename)
    # except Exception as e:
    #     print("Exception occurred: ", e)
    #     api.nuke_all_instances(initial_ec2, ['i-035f88ca820e399e7']) # TODO: this assumes that all instances were created in initial_ec2, which is not necessarily true. fix this later.
    #     raise e

    # print(pretty_json(instance_list))

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