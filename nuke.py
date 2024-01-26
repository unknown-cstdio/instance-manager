import api
initial_ec2, initial_ce = api.choose_session(is_UM_AWS=True, region='us-east-1')
# Excluded instances:
snowflake_broker = "i-000e0aa574309854c"
snowflake_proxy = "i-036fe9a028070f9ef"
snowflake_proxy2 = "i-0417fc889dd4c103d"
spotproxy_controller = "i-035f88ca820e399e7"
spotproxy_nat = "i-0975320cbe3a681df"
spotproxy_service = "i-0dd2ca9d91838f3c8"
spotproxy_client = "i-0c7adc535b262d69e"
excluded_instances = [snowflake_broker, snowflake_proxy, snowflake_proxy2, spotproxy_controller, spotproxy_nat, spotproxy_service, spotproxy_client]
api.nuke_all_instances(initial_ec2, excluded_instances)
print("NUKED EVERYTING")