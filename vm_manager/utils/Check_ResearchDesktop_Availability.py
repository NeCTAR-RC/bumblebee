import requests
import pandas as pd
import re
from io import StringIO

CORES_LIST = [4.0, 8.0]
RAM_GB_LIST = [16.0, 32.0]
HYPERVISOR_LOG = 'https://swift.rc.nectar.org.au:8888/v1/AUTH_42/hypervisor_capacity/hypervisor_capacity.log'
AGG = 'qh2-uom_production'


def check_availability():
    availability = ""
    request = requests.get(HYPERVISOR_LOG)
    content = str(request.content)
    content = content.encode().decode('unicode_escape')

    # Strip out date metadata before the start of '|' table
    content = content[content.find('|'):]

    # Strip out the stuff after the '|' table
    content = content[0:content.find('\\n \\nCell Totals')]

    content = re.sub('\\n', '\n', content)
    content = re.sub(' +', ' ', content)

    data = StringIO(content)

    dataframe = pd.read_csv(data, sep='|')
    cols = ['Cell', 'Host', 'Status', 'PCPUs', 'LCPUs', 'VCPUs', 'VCPU_Free', 'RAM', 'RAM_Free', 'VM_Count', 'Agg']
    dataframe.columns = cols

    # Filter for nodes that can fit a desktop
    for cores, ram in zip(CORES_LIST, RAM_GB_LIST):
        availability += f"\nFor Desktop Flavor {cores} cores and {ram}GB RAM: \n"
        nodes_df = dataframe[
            (dataframe['VCPU_Free'] >= cores) &
            (dataframe['RAM_Free'] >= ram) &
            (dataframe['Agg'].str.contains(AGG))].copy()

        nodes_df['by_cores'] = nodes_df.apply(lambda x: int(x['VCPU_Free'] / cores), axis=1)
        nodes_df['by_ram'] = nodes_df.apply(lambda x: int(x['RAM_Free'] / ram), axis=1)
        nodes_df['possible_rd'] = nodes_df.apply(lambda x: min(x['by_cores'], x['by_ram']), axis=1)

        num_nodes = len(nodes_df)
        num_rd = nodes_df['possible_rd'].sum()
        nodes_df_host = nodes_df['Host'].array

        availability += f"{num_rd} desktops available across {num_nodes} nodes \n"

        availability += "Hosts:"
        availability += '\n'.join(nodes_df['Host'].array)
    return availability
