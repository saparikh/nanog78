import os

try:
    from pybfe.datamodel.policy import (
        STATUS_FAIL, STATUS_PASS
    )
    TEST_STATUS_FAIL = STATUS_FAIL
    TEST_STATUS_PASS = STATUS_PASS
except:
    TEST_STATUS_PASS = u"Pass"
    TEST_STATUS_FAIL = u"Fail"


def record_results(bf, assertion, pass_message, fail_message):

    session_type = os.environ.get('SESSION_TYPE')

    if assertion:
        if session_type == 'bfe':
            bf.asserts._record_result(True, status=STATUS_PASS,
                                      message=pass_message)
    else:
        if session_type == 'bfe':
            bf.asserts._record_result(False, status=STATUS_FAIL,
                                      message=fail_message)
        raise AssertionError(fail_message)


def get_node_cfg_files(bf, node):
    """Return a list of config files that contributed to the configuration of the given node"""
    file_list = []
    fpStatus = bf.q.fileParseStatus().answer().frame()
    for _, row in fpStatus.iterrows():
        if node in row['Nodes']:
            file_list.append(row['File_Name'])

    return file_list

def get_def_rp_structs(bf, node):
    """Return a dataframe with the defined Structures for the given node"""
    df = bf.q.definedStructures(nodes=node).answer().frame()

    return df

def get_struct_cfg_lines(bf, node, struct_name):
    """Return the source file and line numbers for the given structure for the given node"""

    df1 = bf.q.definedStructures(nodes=node).answer().frame()
    df2 = df1[df1['Structure_Name'] == struct_name]

    if df2.empty:
        return None, None
    else:
        return df2[df2['Structure_Name'] == struct_name].iloc[0].Source_Lines.filename, \
               df2[df2['Structure_Name'] == struct_name].iloc[0].Source_Lines.lines

def get_ref_rp_structs(bf, node, struct_name):
    """Return a dataframe with the structures that are referenced within the given structure on the given node"""

    f, lines = get_struct_cfg_lines(bf, node, struct_name)
    df1 = bf.q.referencedStructures(nodes=node).answer().frame()

    # assumes device configuration is contained in a single file
    # should not be an issue since BF at the moment since only supports multi-file input for AWS,
    # not for any traditional networking gear
    if f and lines:
        df2 = df1[df1['Source_Lines'].apply(lambda x: (x.filename == f) & (len(set(lines).intersection(x.lines)) != 0))]
    else:
        df2 = pd.DataFrame
    return df2
