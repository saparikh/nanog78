from .test_utils import record_results, get_ref_rp_structs
import pytest
from netaddr import IPNetwork
from os.path import abspath, dirname, realpath
import json
from pybatfish.datamodel import HeaderConstraints, Interface
import pandas as pd
import yaml

@pytest.fixture(scope='module')
def customer_list():

    _this_dir = abspath(dirname(realpath(__file__))) # directory in which this file is present
    _file = f"{_this_dir}/customer_list.yml"

    with open(_file, 'r') as f:
        customer = yaml.safe_load(f)

    return customer

@pytest.fixture(scope='module')
def bogon_prefixes():
    """No prefixes from this list should be accepted from external BGP peers"""

    bogon = [
        # BOGON
        "0.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "192.0.2.0/24",
        "224.0.0.0/3",
        # RFC1918
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16"
    ]
    return bogon

@pytest.fixture(scope='module')
def routing_structs():

    structure_types = {
        # need to look into juniper policy-statement and IOS-XR route-policy clauses to see if that needs to be recursively analyzed
        'prefix-list': [
            'prefix_list',
            'ip_prefix_list',
            'ipv4_prefix_list',
            'ip prefix_list',
            'ipv4 prefix-list',
            'prefix-set',
            'prefix-list'
        ],
        'as-path': [
            'as-path-list',
            'as-path-group',
            'as-path',
            'as-path-group as-path'
            'ip as-path access-list',
            'as-path access-list',
            'as-path-set'
        ]
    }
    return structure_types

@pytest.fixture(scope='module')
def bgpPeer(bf):
    return bf.q.bgpPeerConfiguration().answer().frame()

def customer_node(bf, ip_address):
    """Given an IP address (not prefix) return name of the node that owns it"""
    df = bf.q.ipOwners().answer().frame()

    df = df[df['IP']==ip_address]
    if df.empty:
        return None
    elif len(df) >1:
        return None
    else:
        return df.iloc[0]['Node']


def test_customer_bgp_session_input_policy(bf, customer_list):
    """Ensure all customer BGP peering sessions have INPUT policy configured"""

    bf.asserts.current_assertion = 'Assert all customer BGP sessions have input route policy'

    # determine the list of peering nodes which need to be evaluated
    nodes = []
    for customer in customer_list:
        nodes.append(customer['Node'])
    nodespec = ','.join(nodes)

    # retrieve the BGP session configuration for all peers on the peering nodes
    df = bf.q.bgpPeerConfiguration(nodes=nodespec).answer().frame()
    bad_peers_in = []

    for customer in customer_list:
        # check the BGP session configuration for specific peers and extract input routing policy
        iPol = df[(df['Node'] == customer['Node']) & (df['Remote_IP'] == customer['Remote_IP'])]['Import_Policy']
        if len(iPol.iloc[0]) == 0:
            bad_peers_in.append(f"{customer['Node']}:{customer['Remote_IP']}")

    test = (len(bad_peers_in) == 0)
    pass_message = "All customer BGP sessions have input route policy configured\n"
    fail_message = f"Customer BGP sessions without input route policy\n{bad_peers_in}"

    record_results(bf, test, pass_message, fail_message)

def test_customer_bgp_session_aspath_filter(bf, customer_list, routing_structs):
    """Check if an AS PATH filter has been used for the input policy for customer BGP sessions"""

    bf.asserts.current_assertion = 'Assert all customer BGP peers use ASPATH filtering in'

    # NOTE:
    #   This scheme doesn't check if the ASPATH filter is correct or even non-empty
    #   Also, for Cisco IOS devices where you apply distribute-lists, route-maps and prefix-lists simultaneously to neighbors
    #   this scheme won't work.
    missing = []

    for customer in customer_list:
        node = customer['Node']
        peer_ip = customer['Remote_IP']

        bgpPeer = bf.q.bgpPeerConfiguration(nodes=node).answer().frame()

        peer = bgpPeer[(bgpPeer['Node'] == node) & (bgpPeer['Remote_IP'] == peer_ip)]
        # todo need to add check in case no peer is found
        iPol = peer['Import_Policy'].iloc[0]
        if len(iPol) == 0:
            missing += (peer[['Node', 'Local_IP', 'Local_AS', 'Remote_IP', 'Remote_AS', 'Import_Policy']].to_dict('records'))
            continue
        else:
            df = get_ref_rp_structs(bf, node, iPol[0])

        if df.empty:
            missing += (peer[['Node', 'Local_IP', 'Local_AS', 'Remote_IP', 'Remote_AS', 'Import_Policy']].to_dict('records'))
        elif len(set(df['Structure_Type']).intersection(routing_structs['as-path'])) == 0:
            missing += (peer[['Node', 'Local_IP', 'Local_AS', 'Remote_IP', 'Remote_AS', 'Import_Policy']].to_dict('records'))

    test = (len(missing) == 0)
    pass_message = "All customer BGP import policies reference AS PATH filters\n"
    fail_message = f"List of customer BGP sessions with import policies missing AS PATH filters\n\n{pd.DataFrame(missing)}"

    record_results(bf, test, pass_message, fail_message)

def test_customer_bgp_session_pfx_filter(bf, customer_list, routing_structs):
    """Check if an prefix filter has been used for the input policy for customer BGP sessions"""

    bf.asserts.current_assertion = 'Assert all customer BGP peers use prefix-list filtering in'

    # NOTE:
    #   This scheme doesn't check if the prefix filter is correct or even non-empty
    #   Also, for Cisco IOS devices where you apply distribute-lists, route-maps and prefix-lists simultaneously to neighbors
    #   this scheme won't work.

    missing = []

    for customer in customer_list:
        node = customer['Node']
        peer_ip = customer['Remote_IP']

        bgpPeer = bf.q.bgpPeerConfiguration(nodes=node).answer().frame()

        peer = bgpPeer[(bgpPeer['Node'] == node) & (bgpPeer['Remote_IP'] == peer_ip)]
        # todo need to add check in case no peer is found

        iPol = peer['Import_Policy'].iloc[0]
        if len(iPol) == 0:
            missing += (peer[['Node', 'Local_IP', 'Local_AS', 'Remote_IP', 'Remote_AS', 'Import_Policy']].to_dict('records'))
            continue
        else:
            df = get_ref_rp_structs(bf, node, iPol[0])

        if df.empty:
            missing += (peer[['Node', 'Local_IP', 'Local_AS', 'Remote_IP', 'Remote_AS', 'Import_Policy']].to_dict('records'))
        elif len(set(df['Structure_Type']).intersection(routing_structs['as-path'])) == 0:
            missing += (peer[['Node', 'Local_IP', 'Local_AS', 'Remote_IP', 'Remote_AS', 'Import_Policy']].to_dict('records'))

    test = (len(missing) == 0)
    pass_message = "All customer BGP import policies reference prefix-list filters\n"
    fail_message = f"List of customer BGP sessions with import policies missing prefix-list filters\n\n{pd.DataFrame(missing)}"

    record_results(bf, test, pass_message, fail_message)

def test_customer_routes_have_communities(bf, customer_list):
    """Check that all customer BGP routes have at least 1 community set"""
    bf.asserts.current_assertion = 'Assert all customer BGP routes have a community set'

    nodes = []
    for customer in customer_list:
        nodes.append(customer['Node'])
    nodespec = ','.join(nodes)

    df = bf.q.routes(rib='bgp', nodes=nodespec).answer().frame()
    missing_comm = []
    for customer in customer_list:
        for _, row in df.iterrows():
            if (row['Node'] == customer['Node']) & (row['Next_Hop_IP'] == customer['Remote_IP']):
                if len(row['Communities']) == 0:
                    missing_comm.append(f"Prefix {row['Network']} from {customer['Remote_IP']} on {customer['Node']}")

    test = (len(missing_comm) == 0)
    pass_message = "All customer BGP routes have a community set\n"
    fail_message = f"List of customer routes missing communities\n{missing_comm}"

    record_results(bf, test, pass_message, fail_message)

def test_customer_routes_prefix_length(bf, customer_list):
    """Check that no routes accepted from customers have a prefix length > /24"""
    bf.asserts.current_assertion = 'Assert no customer routes have prefix length longer then /24'

    nodes = []
    for customer in customer_list:
        nodes.append(customer['Node'])
    nodespec = ','.join(nodes)

    df = bf.q.routes(rib='bgp', nodes=nodespec).answer().frame()
    pfx_len = []

    for customer in customer_list:
        for _, row in df.iterrows():
            if (row['Node'] == customer['Node']) & (row['Next_Hop_IP'] == customer['Remote_IP']):
                _pfx, _len = row['Network'].split('/')
                if int(_len) > 24:
                    pfx_len.append(f"Prefix {row['Network']} from {customer['Remote_IP']} on {customer['Node']}")

    test = (len(pfx_len) == 0)
    pass_message = "All customer BGP routes have a prefix length <= /24\n"
    fail_message = f"List of customer routes with prefix length > /24\n{pfx_len}"

    record_results(bf, test, pass_message, fail_message)

def test_customer_bogon_routes(bf, customer_list):
    """Check that no BOGON routes are accepted from customers"""
    bf.asserts.current_assertion = 'Assert no BOGON prefixes accepted from customers'

    df = bf.q.routes(rib='bgp').answer().frame() #retrieve BGP RIB for all devices
    bogons = []

    for customer in customer_list:
        for _, row in df.iterrows():
            if (row['Node'] == customer['Node']) & (row['Next_Hop_IP'] == customer['Remote_IP']): #found routes learnt from customer
                z = IPNetwork(row['Network'])
                if (z.is_reserved() or z.is_private() or z.is_loopback() or z.is_link_local() or z.is_multicast()):
                    bogons.append(
                        f"Prefix {row['Network']} from {customer['Remote_IP']} on {customer['Node']} should not be accepted")

    test = (len(bogons) == 0)
    pass_message = "No BOGON prefixes accepted from customers\n"
    fail_message = f"List of BOGON prefixes accepted from customers\n\n{bogons}"

    record_results(bf, test, pass_message, fail_message)

def test_advertise_long_prefix_length(bf, customer_list):
    """Test to ensure that no prefixes of length /24 or longer are sent to external BGP peers"""

    bf.asserts.current_assertion = 'Assert no routes sent to BGP peers has a prefix length longer then /24'

    df = bf.q.routes(rib='bgp').answer().frame()
    pfx_len = []

    for customer in customer_list:
        target_node = customer_node(bf, customer['Remote_IP'])
        if target_node is None:
            continue
        for _, row in df.iterrows():
            if (row['Node'] == target_node):
                _pfx, _len = row['Network'].split('/')
                if int(_len) > 24:
                    pfx_len.append(f"Prefix {row['Network']} sent to {target_node}:{customer['Remote_IP']} from {customer['Node']}")

    test = (len(pfx_len) == 0)
    pass_message = "All BGP routes sent to peers have prefix length <= /24\n"
    fail_message = f"List of peers with BGP routes with prefix length > /24\n\n{pfx_len}"

    record_results(bf, test, pass_message, fail_message)

def test_customer_routes_valid(bf, customer_list):
    """Check that no routes accepted from customers that are not from the agreed upon prefix range"""
    bf.asserts.current_assertion = 'Assert no customer routes received outside of agreed upon prefix range'

    nodes = []
    for customer in customer_list:
        nodes.append(customer['Node'])
    nodespec = ','.join(nodes)

    bgpRib = bf.q.routes(rib='bgp', nodes=nodespec).answer().frame()

    extra_pfx = []
    for customer in customer_list:
        df = bgpRib[bgpRib['Node'] == customer['Node']]
        for _, row in df.iterrows():
            if (row['Next_Hop_IP'] == customer['Remote_IP']):
                if not any(IPNetwork(row['Network']) in IPNetwork(pfx) for pfx in customer.get('Origin_Prefixes', ["0.0.0.0"]) ):
                    extra_pfx.append(f"{row['Network']} on {customer['Node']} from {customer['Remote_IP']}")

    test = (len(extra_pfx) == 0)
    pass_message = "No customer BGP peers sending routes outside of agreed upon prefix range\n"
    fail_message = f"List of offending routes outside of agreed upon prefix range\n\n{extra_pfx}"

    record_results(bf, test, pass_message, fail_message)

def test_customer_link_input_filter(bf, customer_list, bgpPeer):
    """Check that all customer interfaces have an input filter set"""
    bf.asserts.current_assertion = 'Assert all customer connections have an input filter applied'

    missing = []
    for customer in customer_list:
        df = bf.q.resolveInterfaceSpecifier(interfaces = f"@connectedTo({customer['Remote_IP']})", nodes=customer['Node']).answer().frame()
        # this only works for numbered interfaces and BGP peers
        if not df.empty:
            local_intf = df.iloc[0].Interface
        else:
            missing.append(f"Error: Bad specifier. @connectedTo({customer['Remote_IP']}, "
                           f"Cannot find local interface on {customer['Node']} connecting to IP:{customer['Remote_IP']} AS:{customer['Remote_AS']}")
            continue

        df2 = bf.q.interfaceProperties(interfaces=str(local_intf)).answer().frame()

        if df2.empty:
            missing.append(f"Error: No Interface Properties for {local_intf}, "
                           f"on {customer['Node']} connecting to IP:{customer['Remote_IP']} AS:{customer['Remote_AS']}")
            continue

        input_acl = df2.iloc[0]['Incoming_Filter_Name']

        if df2.iloc[0]['Incoming_Filter_Name'] is None:
            missing.append(f"{local_intf} connecting to IP:{customer['Remote_IP']} AS:{customer['Remote_AS']}")
            continue

    test = (len(missing) == 0)
    print_fail = "\n".join(missing)
    pass_message = "All customer connections have an input filter applied\n"
    fail_message = f"List of customer connections with missing input filters\n{print_fail}"

    record_results(bf, test, pass_message, fail_message)

def test_customer_link_input_filter_anti_spoofing(bf, customer_list, bgpPeer):
    """Check that all customer input filters only allowed specified source IP addresses"""
    bf.asserts.current_assertion = 'Assert all customer input filters only allow specified source IP addresses'

    missing = []
    for customer in customer_list:
        df = bf.q.resolveInterfaceSpecifier(interfaces = f"@connectedTo({customer['Remote_IP']})", nodes=customer['Node']).answer().frame()
        # this only works for numbered interfaces and BGP peers
        if not df.empty:
            local_intf = df.iloc[0].Interface
        else:
            missing.append(f"Bad specifier: @connectedTo({customer['Remote_IP']}, Cannot find local interface for {customer}")
            continue

        df2 = bf.q.interfaceProperties(interfaces=str(local_intf)).answer().frame()

        if df2.empty:
            missing.append(f"No Interface Properties for {local_intf}, Cannot find local interface for {customer}")
            continue

        input_acl = df2.iloc[0]['Incoming_Filter_Name']

        if df2.iloc[0]['Incoming_Filter_Name'] is None:
            missing.append(f"No ACL applied to {local_intf} connecting to {customer}")
            continue

        in_acl = df2.iloc[0]['Incoming_Filter_Name']
        filter_spec = f"@in({df2.iloc[0]['Interface']})"
        srcIps = ",".join(customer.get('Origin_Prefixes', ["0.0.0.0/0"]))
        headers = HeaderConstraints(srcIps=srcIps)
        df3 = bf.q.searchFilters(action='permit', headers=headers, filters=filter_spec).answer().frame()

        if df3.empty:
            continue
        else:
            missing.append(f"ACL {in_acl} on {local_intf} connecting to {customer} does not prevent spoofing\n\n{df3}\n")

    # need to check anti-spoofing here

    test = (len(missing) == 0)
    print_fail = "\n".join(missing)
    pass_message = "All customer input filters prevent spoofing\n"
    fail_message = f"List of customer connections with filters that do not prevent spoofing\n{print_fail}"

    record_results(bf, test, pass_message, fail_message)

def test_all_bgp_sessions_up(bf):
    bf.asserts.assert_no_unestablished_bgp_sessions()