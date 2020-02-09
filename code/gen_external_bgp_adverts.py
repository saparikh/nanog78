import json
from random import randint
from copy import deepcopy
from netaddr import *
import pathlib
from deepdiff import DeepDiff

DEBUG = False
PDEBUG = False

def convert_well_known_communities(community):
    """Convert well known communities from string to ASPLAIN"""

    comm_map = {
        "No-Export": "65535:65281",
        "No-Advertise": "65535:65282",
        "Local-AS": "65535:65283",
        "No-Peer": "65535:65284"
    }

    return comm_map.get(community, community)

def gen_random_as_path(asn):
    """Generate a random ASPATH"""
    if asn:
        t_aspath = [asn]
    else:
        t_aspath = []
    for _ in range(randint(0,16)):
        t_asn = randint(0,16000)
        if t_asn != asn:
            t_aspath.append( [t_asn] )

    if PDEBUG:
        print(t_aspath)
    return t_aspath

def create_bf_bgp_advert(src_as, src_node, src_peer, dst_node, dst_peer, pfx_scopes, community_list, originate, pfx_count=None):
    """Convert generic BGP advertisement to Batfish format BGP announcement"""
    base_bgp_advert = {
                "type": "ebgp_sent", "srcProtocol": "AGGREGATE", "originType": "egp",
                "originatorIp": "0.0.0.0",  "srcVrf": "default",
                "dstVrf": "default", "clusterList": [],
                'communities': [], 'asPath': [], 'localPreference': 100,
                'med': 5, 'network': "", 'nextHopIp': "",
                'srcNode': "", 'dstNode': "",
                'srcIp': "", 'dstIp': ""
            }

    bf_bgp_advert = {
        "Announcements": [ ]
    }

    bgp_advert = gen_bgp_advert(pfx_scopes, pfx_count)

    for prefix in bgp_advert['prefix']:

        if PDEBUG:
            print(f"{[src_as] + bgp_advert['asPath']}")
        new_bgp_advert = deepcopy(base_bgp_advert)
        new_bgp_advert['communities'] = community_list
        new_bgp_advert['asPath'] = [src_as] if originate else [src_as] + bgp_advert['asPath']
        new_bgp_advert['localPreference'] = randint(0, 100)
        new_bgp_advert['med'] = randint(0, 50)
        new_bgp_advert['network'] = prefix
        new_bgp_advert['nextHopIp'] = src_peer
        new_bgp_advert['srcNode'] = src_node
        new_bgp_advert['dstNode'] = dst_node
        new_bgp_advert['srcIp'] = src_peer
        new_bgp_advert['dstIp'] = dst_peer

        bf_bgp_advert['Announcements'].append(new_bgp_advert)

    return bf_bgp_advert

def gen_prefix(scopes, pfx_count=None):
    """Generate list of prefixes"""

    if pfx_count:
        max_pfx_cnt = pfx_count
    else:
        max_pfx_cnt = 16

    max_pfx_len = 27
    min_pfx_len = 8

    subnets = []
    for scope in scopes:
        count = randint(1, max_pfx_cnt)
        pfx = IPNetwork(scope)
        pfx_len = randint(max(min_pfx_len, pfx.prefixlen), max(max_pfx_len, pfx.prefixlen))
        # guards against a scope that has a longer prefix length then min_pfx_len or shorter prefix length then max_pfx_len
        max_pfx = len(list(pfx.subnet(pfx_len)))
        count = min(max_pfx, count)
        # ensures count doesn't exceed the maximum number of subnets of pfx_len that can exist under pfx
        if PDEBUG:
           print(f"{pfx}, {pfx_len}, {count}")
           subnets.append(list(pfx.subnet(pfx_len, count=count)))
        subnets += [str(x) for x in list(pfx.subnet(pfx_len, count=count)) if True]

    if PDEBUG:
        print(subnets)
    return subnets

def gen_bgp_advert(user_pfx_scopes, pfx_count=None):
    """Generate a generic BGP advertisement"""
    base_pfx_scopes = [
        '12.0.0.0/12',
        '2.0.0.0/9',
        '24.1.0.0/10',
        '128.0.0.0/25',
        '144.0.0.0/17',
        '9.0.0.0/7',
        '164.0.0.0/22'
    ]

    if len(user_pfx_scopes) != 0:
        pfx_scopes = user_pfx_scopes
    else:
        pfx_scopes = base_pfx_scopes

    _bgp_advert = {
        "prefix": gen_prefix(pfx_scopes, pfx_count),
        "med": randint(0,50),
        "localPreference": randint(0,100),
        "originType": "egp",
        "communities": [],
        "asPath": gen_random_as_path(None),
        "originatorIp": '0.0.0.0'
    }

    return _bgp_advert

def save_bgp_routes_to_disk(bgp_route, snapshot_path, overwrite):

    bgp_announcements = f"{snapshot_path}/external_bgp_announcements.json"

    if not pathlib.Path(bgp_announcements).exists():
        with open(bgp_announcements, 'w') as f:
            json.dump(bgp_route, f)
    elif overwrite:
        with open(bgp_announcements, 'w') as f:
            json.dump(bgp_route, f)
    else:
        with open(bgp_announcements, 'r') as f:
            t = json.load(f)
        t['Announcements'] += bgp_route['Announcements']
        with open(bgp_announcements, 'w') as f:
            json.dump(t, f)

def get_new_announmenents(base_bgp_announce, test_bgp_announce):
    diff_bgp_adj_rib_in = DeepDiff(base_bgp_announce, test_bgp_announce)
    # show prefixes added
    if 'iterable_item_added' in diff_bgp_adj_rib_in.keys():
        print("The following prefixes are part of the new BGP announcement")
        for k, v in diff_bgp_adj_rib_in['iterable_item_added'].items():
            print(f"{v['network']} advertised to {v['dstNode']}:{v['dstIp']}")
    else:
        print("No new prefixes")
def get_removed_announcements(base_bgp_announce, test_bgp_announce):
    diff_bgp_adj_rib_in = DeepDiff(base_bgp_announce, test_bgp_announce)
    # show prefixes removed
    if 'iterable_item_removed' in diff_bgp_adj_rib_in.keys():
        print("The following prefixes are have been removed from the new BGP announcement")
        for k, v in diff_bgp_adj_rib_in['iterable_item_removed'].items():
            print(f"{v['network']} withdrawn from {v['dstNode']}:{v['dstIp']}")
    else:
        print("No prefixes were removed")