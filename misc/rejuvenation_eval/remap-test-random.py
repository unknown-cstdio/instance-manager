## Just to understand how AWS remap charges work..

import time 
import calendar
import sys, os
import threading
import math
import json
import warnings
from collections import defaultdict
sys.path.append("../../")
import api

zone = "us-east-1a"
region = zone[:-1]
proxy_impl = "wireguard"
instance_type = "t3.micro"
iterations = 30 # one iteration goes through both NICs

def ping(ip, backoff_time, trials):
    """
        Parameters:
            ip: string
            backoff_time: int # seconds
            trials: int
        Returns:
            True if ping is successful, False otherwise
    """
    for i in range(trials):
        response = os.system("ping -c 1 " + ip)
        if response == 0:
            return 0
        else:
            time.sleep(backoff_time)
    return 1

def ping_instances(ec2, ip, multi_NIC=True, not_fixed=True):
    """
        Checks if instances are pingable.

        Parameters:
            nic_list: list of NIC IDs
            not_fixed: True | False
                - True: # TODO Minor quirk that will be removed later: only the default NIC (i.e., original_nic) is configured to accept pings for now. We will need to fix this later. Will remove this parameter altogether once fixed. 
    """
    failed_ips = []

    # Retry details:
    backoff_time = 10 # seconds
    trials = 3

    response = ping(ip, backoff_time, trials)
    if response == 0:
        print(f"{ip} is up!")
    else:
        print(f"{ip} is down!")
        # if ping fails, add to failed_ips
        failed_ips.append(ip)
    return failed_ips


ec2, ce = api.choose_session(is_UM_AWS=True, region=region)
launch_template = api.use_UM_launch_templates(ec2, region, proxy_impl, "main")

# SECTION: Create two instances
# Create the initial fleet (2 instances) 
response = api.create_fleet(ec2, instance_type, zone, launch_template, 2)
time.sleep(30) # wait awhile for fleet to be created
# make sure that the required instances have been acquired: 
print(response['FleetId'])
print(api.pretty_json(response))
all_instance_details = api.get_specific_instances_with_fleet_id_tag(ec2, response['FleetId'], "raw") 
if len(all_instance_details) != 2:
    warnings.warn("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(instances_to_create) + " were required.")
    print_stdout_and_filename("Not enough instances were created: only created " + str(len(all_instance_details)) + " instances, but " + str(instances_to_create) + " were required.", print_filename)

# SECTION: Create 1 EIP and attach it to the first instance's NIC. 
eip = api.get_eip_id_from_allocation_response(api.allocate_address(ec2))
ip = api.get_public_ip_address(ec2, eip)
assoc_id = ""

nics = []
for index, original_instance_details in enumerate(all_instance_details): # only create 1 EIP
    instance = original_instance_details['InstanceId']
    original_nic = original_instance_details['NetworkInterfaces'][0]['NetworkInterfaceId']
    nics.append((instance, original_nic))

# print(nics)

# SECTION: Perform remap operations: disassociate the EIP from the first NIC and associate the EIPs to the second NIC. Repeat 200 times. 
# Get the 2 NICs of the 2 instances: 
for i in range(iterations):
    print("Iteration: " + str(i))
    # Disassociate the EIP from the first NIC
    for index, nic_details in enumerate(nics):
        instance = nic_details[0]
        nic = nic_details[1]
        assoc_id = api.get_association_id_from_association_response(api.associate_address(ec2, instance, eip, nic))
        time.sleep(15)
        failed_ips = ping_instances(ec2, ip, multi_NIC=False)
        if len(failed_ips) != 0:
            print("Failed to ssh/ping into instances: " + str(failed_ips))
            raise Exception("Failed to ssh/ping into instances: " + str(failed_ips))

        api.disassociate_address(ec2, assoc_id)

api.release_address(ec2, eip)
# Delete everything..