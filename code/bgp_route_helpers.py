import json
from copy import deepcopy
from netaddr import IPNetwork

import pandas as pd
from pybatfish.datamodel.route import BgpRoute

PDEBUG = False
DEBUG = False


def parseAsSet(txt):
    if txt[0] == '{':
        return [int(elem) for elem in txt[1:-1].split(',')]
    return [int(txt)]


def parseAsPath(txt):
    return [parseAsSet(elem)
            for elem in txt.strip().split(' ')
            if elem]


def communityStrToInt(comm):
    [upper, lower] = comm.split(':')
    return (int(upper) << 16) + int(lower)


def originProtocolToOriginType(proto):
    if proto == 'bgp':
        return 'egp'
    if proto == 'ibgp':
        return 'igp'
    return 'incomplete'


def rowToBgpRoute(row):
    asPath = parseAsPath(row['AS_Path'])
    communities = [communityStrToInt(comm) for comm in row['Communities']]
    originType = originProtocolToOriginType(row['Origin_Protocol'])
    return BgpRoute(
        communities=communities,
        asPath=asPath,
        localPreference=row['Local_Pref'],
        network=row['Network'],
        protocol=row['Protocol'],
        metric=row['Metric'],
        originatorIp='0.0.0.0',
        originType=originType)


def bgpRib_to_bgpRoutes(bf, node, vrf):
    """Convert the BGP Local RIB on a node for a VRF to a list of BgpRoute (pybatfish.datamodel.route.BgpRoute)"""
    df = bf.q.routes(rib='bgp', nodes=node, vrfs=vrf).answer().frame()
    rt = []
    for _, row in df.iterrows():
        rt.append(rowToBgpRoute(row))

    return rt


def get_bgp_policy_name(bf, node, neighbor, direction, snapshot_name=None):
    """Retrieve the BGP policy applied as input or output policy for a peer in a given snapshot"""

    # assumes:
    #  - `default` VRF and `ipv4UnicastAddressFamily
    #  - active peers that are not BGP unnumbered

    # vim['pe1']['vrfs']['default']['bgpProcess']['neighbors']['9.1.1.1/32']['ipv4UnicastAddressFamily'].keys()
    # Out[416]: dict_keys(
    #     ['addressFamilyCapabilities', 'exportPolicy', 'exportPolicySources', 'importPolicy', 'importPolicySources',
    #      'routeReflectorClient'])

    if not snapshot_name:
        snapshot_name = bf.snapshot

    vim = bf.q.viModel().answer(snapshot=snapshot_name)['answerElements'][0][
        'nodes']
    if direction in ['input', 'in']:
        policy_key = 'importPolicy'
        if PDEBUG: print("Import Policy")
    elif direction in ['output', 'out', 'export']:
        policy_key = 'exportPolicy'
        if PDEBUG: print("Export Policy")
    else:
        return ""

    peer = f"{neighbor}/32"
    policy = vim[node]['vrfs']['default']['bgpProcess']['neighbors'][peer][
        'ipv4UnicastAddressFamily'][policy_key]

    return policy


def compare_named_route_policies_single_snapshot(bf, node, base_policy,
                                                 new_policy, direction, routes):
    """Identify differences between 2 BGP routing policies on a given node in the same snapshot

        Keyword arguments:
        bf -- Batfish or Batfish Enterprise Session object (bf.Session)
        node -- the name of the node (str)
        base_policy -- the name of the base routing policy to evaluate (str)
        new_policy -- the name of the new routing policy to evaluate (str)
        direction -- are these input or output policies
        routes -- list of BgpRoutes to evaluate the policies against (list of pybatfish.datamodel.route.BgpRoute)
    """
    test1 = bf.q.testRoutePolicies(nodes=node, policies=base_policy,
                                   direction=direction,
                                   inputRoutes=routes).answer().frame()
    test2 = bf.q.testRoutePolicies(nodes=node, policies=new_policy,
                                   direction=direction,
                                   inputRoutes=routes).answer().frame()
    bgp_diff = []
    for index, row in test1.iterrows():
        if row['Action'] != test2.iloc[index]['Action']:
            t = {
                "Route": row['Input_Route'].network,
                "Old Action": row['Action'],
                "Old Transformation": row['Difference'],
                "New Action": test2.iloc[index]['Action'],
                "New Transformation": test2.iloc[index]['Difference']
            }
            bgp_diff.append(deepcopy(t))
        elif row['Difference'] != test2.iloc[index]['Difference']:
            t = {
                "Route": row['network'],
                "Old Action": row['Action'],
                "Old Transformation": row['Difference'],
                "New Action": test2.iloc[index]['Action'],
                "New Transformation": test2.iloc[index]['Difference']
            }
            bgp_diff.append(deepcopy(t))

    bgp_df = pd.DataFrame(bgp_diff)
    return bgp_df


def compare_bgp_peer_policies(bf, node, peer, base_snapshot, new_snapshot,
                              direction, routes):
    """Identify differences between 2 BGP routing policies on a given node across 2 snapshots

        Keyword arguments:
        bf -- Batfish or Batfish Enterprise Session object (bf.Session)
        node -- the name of the node (str)
        base_snapshot -- the name of the base snapshot (str)
        new_snapshot -- the name of the new snapshot (str)
        direction -- are these input or output policies
        routes -- list of BgpRoutes to evaluate the policies against (list of pybatfish.datamodel.route.BgpRoute)
    """
    base_policy = get_bgp_policy_name(bf, node, peer, direction, base_snapshot)
    new_policy = get_bgp_policy_name(bf, node, peer, direction, new_snapshot)

    if PDEBUG:
        print(f"Base Policy: {base_policy}\n")
        print(f"New Policy: {new_policy}\n")

    test1 = bf.q.testRoutePolicies(nodes=node, policies=base_policy,
                                   direction=direction,
                                   inputRoutes=routes).answer(
        snapshot=base_snapshot).frame()
    test2 = bf.q.testRoutePolicies(nodes=node, policies=new_policy,
                                   direction=direction,
                                   inputRoutes=routes).answer(
        snapshot=new_snapshot).frame()
    bgp_diff = []
    for index, row in test1.iterrows():
        if row['Action'] != test2.iloc[index]['Action']:
            t = {
                "Route": row['Input_Route'].network,
                "Old Action": row['Action'],
                "Old Transformation": row['Difference'],
                "New Action": test2.iloc[index]['Action'],
                "New Transformation": test2.iloc[index]['Difference']
            }
            bgp_diff.append(deepcopy(t))
        elif row['Difference'] != test2.iloc[index]['Difference']:
            t = {
                "Route": row['Input_Route'].network,
                "Old Action": row['Action'],
                "Old Transformation": row['Difference'],
                "New Action": test2.iloc[index]['Action'],
                "New Transformation": test2.iloc[index]['Difference']
            }
            bgp_diff.append(deepcopy(t))

    bgp_df = pd.DataFrame(bgp_diff)
    return bgp_df


def convert_ext_bgp_to_bgp_route(bf, target_node, target_peer, ext_routes):
    """Convert BF formatted external_bgp_announcements.json to BF BgpRoute objects
        for a specified target node and peer. Only works for default VRF and numbered active BGP peers.
    """

    # Algorithm:
    # loop thru external_bgp_announcements
    # find ones that have `dstNode` == target_node and `srcIp` == target_peer
    # create BgpRoute object for each announcement

    # use `network`, `asPath`, `localPreference` as is
    # map `med` to `metric`
    # convert `communities` from list of str to list of int
    # default values for `originType:egp`, `originatorIp:0.0.0.0`, `protocol:bgp`, `sourceProtocol:None`

    bgp_routes = []
    for ext_route in ext_routes:
        if ext_route['dstNode'] == target_node and ext_route[
            'srcIp'] == target_peer:
            _communities = []
            for community in ext_route['communities']:
                _communities.append(communityStrToInt(community))

            _bgpRoute = BgpRoute(
                network=ext_route['network'],
                originatorIp='0.0.0.0',
                originType='egp',
                protocol='bgp',
                asPath=ext_route['asPath'],
                communities=_communities,
                localPreference=ext_route['localPreference'],
                metric=ext_route['med'],
                sourceProtocol=None
            )

            bgp_routes.append(_bgpRoute)

    return bgp_routes


def get_snapshot_bgp_announcements(snapshot_path):
    """Returns the BGP announcements that were part of the snapshot"""

    bgp_file = f"{snapshot_path}/external_bgp_announcements.json"
    return get_bgp_announcements(bgp_file)


def get_bgp_announcements(bgp_file):
    """Returns the BGP announcements from the provided file"""
    try:
        with open(bgp_file, 'r') as f:
            t = json.load(f)
    except:
        return []

    return t


def find_newly_denied_routes(rt):
    if len(rt) != 0:
        r = rt[(rt['Old Action'] == 'PERMIT') & (rt['New Action'] == 'DENY')]
        r.loc[:, "Old Transformation"] = r["Old Transformation"].map(
            lambda x: [d.dict() for d in x.diffs])
        return r
    else:
        return rt


def find_newly_permitted_routes(rt):
    if len(rt) != 0:
        r = rt[(rt['Old Action'] == 'DENY') & (rt['New Action'] == 'PERMIT')]
        r.loc[:, "New Transformation"] = r["New Transformation"].map(
            lambda x: [d.dict() for d in x.diffs])
        return r
    else:
        return rt


def find_routes_with_attrib_change(rt):
    if len(rt) != 0:
        r = rt[
            (rt['Old Action'] == 'PERMIT') & (rt['New Action'] == 'PERMIT')]
        r.loc[:, "Old Transformation"] = r["Old Transformation"].map(
            lambda x: [d.dict() for d in x.diffs])
        r.loc[:, "New Transformation"] = r["New Transformation"].map(
            lambda x: [d.dict() for d in x.diffs])
        return r
    else:
        return rt


def get_neighbor_as_path(bf, ip):
    """Return BGP ASN for BGP speaker IP"""
    # assumes `Local_AS` is the same for all sessions on the node
    # need to handle the situation where local_as is selectively set for a specific peer

    if DEBUG:
        return [65001]

    bgpPeer = bf.q.bgpPeerConfiguration().answer().frame()
    for _, peer in bgpPeer.iterrows():
        if peer['Local_IP'] == ip:
            return [peer['Local_AS']]

    return ""


def get_node_from_ip(bf, ip):
    """Return node name for BGP speaker IP"""

    # assumes no duplicate IP address assignment
    if DEBUG:
        return "test"
    ipOwn = bf.q.ipOwners().answer().frame()
    df = ipOwn[ipOwn['IP'] == ip]
    if not df.empty:
        return df.iloc[0]['Node']
    else:
        return ""


def get_bgp_route_with_matching_community(bf, community, nodes=None):
    """Return a route from BGP RIB on specified nodes that have a specific community set"""
    if nodes == None:
        spec = ".*"
    else:
        spec = nodes
    df = bf.q.routes(nodes=spec, rib='bgp').answer().frame()

    return df[df['Communities'].apply(lambda x: (community in x))]

def show_bgp_long_pfx_announcements(bgp_announce, prefix):

    pfx = IPNetwork(prefix)
    for bgp in bgp_announce:
        z = IPNetwork(bgp['network'])
        if z.prefixlen > 23:
            if pfx in z.supernet(16):
                print(f"{bgp['network']} advertised to {bgp['dstNode']}:{bgp['dstIp']} by {bgp['srcNode']}:{bgp['srcIp']}")


def get_input_bgp_routes(bf, snapshot_dir, node, peer_ip):
    bgp_announce = get_snapshot_bgp_announcements(snapshot_dir)
    rt = convert_ext_bgp_to_bgp_route(bf, node, peer_ip,
                                      bgp_announce['Announcements'])
    return rt


def get_denied_routes(df):
    # print routes that were denied
    return df[df['Action'] == 'DENY']


def get_permitted_routes(df):
    return df[df['Action'] == 'PERMIT']


def summarize(df):
    df2 = df.copy()
    df2["Network"] = df2.Input_Route.map(lambda x: x.network)
    df2 = df2.drop(['Input_Route', 'Output_Route', "Policy_Name"], axis=1)
    df2 = df2[['Node', "Network", "Action", "Difference"]]
    df2["Difference"] = df2.Difference.map(
        lambda x: [d.dict() for d in x.diffs])
    return df2


def get_permitted_unmodified(df):
    return df[(df['Action'] == 'PERMIT') & (df['Difference'] == None)]

def get_accepted(routes, prefix, nodes=None):
    if nodes:
        t_node = nodes
    else:
        t_node = ['pe1']
    r=routes[(routes.Node.isin(t_node)) & (routes.Network.apply(lambda x: check_pfx_len(x, prefix, 16)))]
    return r[['Node', 'Network', 'Entry_Presence', 'Snapshot_Next_Hop', 'Reference_Next_Hop']]

def get_leaked(routes, prefix, nodes=None):
    if nodes:
        t_node = nodes
    else:
        t_node = ['cust01']
    r=routes[(routes.Node.isin(t_node)) & (routes.Network.apply(lambda x: check_pfx_len(x, prefix, 16)))]
    return r[['Node', 'Network', 'Entry_Presence', 'Snapshot_Next_Hop', 'Reference_Next_Hop']]

def check_pfx_len(pfx, super_net, mask):
    try:
        if IPNetwork(super_net) in IPNetwork(pfx).supernet(mask):
            return True
        else:
            return False
    except:
        return False

def check_routes_for_subnets(bf, prefix, nodes=None):
    if nodes:
        df = bf.q.routes(nodes=nodes).answer().frame()
    else:
        df = bf.q.routes().answer().frame()

    return df[df['Network'].apply(lambda x: check_pfx_len(x, prefix, 16))]
