"""
    Brainstorm solve problems:
        - Problem: want to use multi-cloud, but problem is need long execution time for like a month to obtain historical pricing which we don't have time for... 
        - Potential solution 1: unless azure and gcp also have historical pricing record APIs.. azure seems to have: https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/virtual-machines/spot-vms.md
        - Potential solution 2: go single cloud: the argument for this would be: just to demonstrate that cost arbitrage has utility too.. 
            - More reasoning: we are not focused on multi-cloud like skypilot which wants to have a unified service catalogue, but the point is that make use of spot instances, and their variable pricing to achieve better cost savings.. 
        - Final solution: the idea is that infra rejuvenation introduces interesting dynamics that normal cost arbitrage alone (despite being unique to our setting) would have encountered. With cost savings, we have four bars: two baselines (normal and static spot) and two cost arbitrage related savings (cost arbitrage on single-NIC, and the absolute optimal which is cost arbitrage on multi-NIC). Now, moving on to the rejuvenation anaylsis: with rejuvenations that occur quite infrequently (> 1 hour or more, more specifically, for clouds that do not charge remapping costs 1 hour is already sufficient) live IP holds its benefits because it allows us to rejuvenate fast but also at multi-NIC level costs.  However, when rejuvenations occur more frequently, live IP is not as useful because the hourly cost granularity of elastic IPs (and the cost of remapping is too high), so we have to use instance rejuvenation, and this gives us costs savings at the levle of cost arbitrage of a single-NIC.
            -Two new insights from this analysis:
                - Live IP is actually still useful but for rejuvenation periods that last more than 1 hour based on our analysis of the current clouds
                - Live IP is actually going to be used in the multi-NIC scenario, even if we opt for instance based rejuvenation, because the other non-default NICs will no matter what have to be live IP rejuvenated.  
            - Finally, we note that cost arbitrage analysis (i.e., cost analysis) is only possible through historical record anyway because the time-scales for that are larger (i.e., for cost to change, though this depends on whether we also use multi-cloud..), but we demonstrate for a single month the results that we obtained (showing that we can actually acquire the instances that are the cheapest..)
    Requirements:
        - Difference between optimal and cost savings bars:
            - 
"""

