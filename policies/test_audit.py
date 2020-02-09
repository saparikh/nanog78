from .test_utils import record_results
import os

def test_no_undefined_refs(bf):
    bf.asserts.assert_no_undefined_references()

def test_no_duplicate_ips(bf):
    os.environ['bf_policy_name'] = "Base configuration Hygiene Policies"
    bf.asserts.current_assertion = 'Assert no duplicate IP addresses are configured'

    dup_ips = bf.q.ipOwners(duplicatesOnly=True).answer().frame()

    test = (len(dup_ips.index) == 0)
    pass_message = "No duplicate IP addresses present in the network\n"
    fail_message = f"Found duplicate IP address assignment\n{dup_ips}\n"

    record_results(bf, test, pass_message, fail_message)

def test_proxy_arp(bf):
    os.environ['bf_policy_name'] = "Base configuration Hygiene Policies"
    bf.asserts.current_assertion = 'Assert that proxy ARP is turned off on all interfaces'

    ans = bf.q.interfaceProperties(properties="Proxy_ARP").answer().frame()
    proxy_arp = ans[ans.Proxy_ARP != False]

    test = (len(proxy_arp) == 0)
    pass_message = "Proxy ARP is off for all interfaces"
    fail_message = f"Found interfaces with incorrect proxy ARP setting\n{proxy_arp}\n"
    record_results(bf, test, pass_message, fail_message)


def test_no_forwarding_loops(bf):
    os.environ['bf_policy_name'] = "Base Forwarding Policies"
    bf.asserts.assert_no_forwarding_loops()


