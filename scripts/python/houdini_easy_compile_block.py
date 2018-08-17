import hou
import sys
import os
import re

NodeReference = hou.stringParmType.NodeReference

expression_re = re.compile('\"\.\./[^,]+\"|\"(/obj/)[^,]+\"|\"(obj/)[^,]+\"')

class BlockNodeTypes(object):

    NONE = None
    COMPILE_INPUT = 1
    COMPILE_END = 2
    COMPILE_BEGIN_METADATA = 3
    COMPILE_BEGIN_FEEDBACK = 4
    COMPILE_BEGIN_PIECE = 5

# ---------------- Menu methods
def compile_selection():

    out_nodes = []
    invalid_nodes = []

    for n in hou.selectedNodes():
      get_block_nodes(start_node=n,
                      out_nodes=out_nodes,
                      invalid_nodes=invalid_nodes,
                      recursive=False)

    print "----"
    for n in out_nodes: print n.name()
    print "----"
    for n in invalid_nodes: print n.name()
    print "----"
    
def compile_forloop(node=None):

    out_nodes = []
    invalid_nodes = []
    get_block_nodes(start_node=node,
                    out_nodes=out_nodes,
                    invalid_nodes=invalid_nodes)

    print "----"
    for n in out_nodes: print n.name()
    print "----"
    for n in invalid_nodes: print n.name()
    print "----"

# ----------------

def add_spare_input(node=None, index=0):

    parm_name = "spare_input{}".format(index)
    parm_label = "Spare Input {}".format(index)

    if node.parm(parm_name) is not None:
        return node.parm(parm_name)

    template_grp = node.parmTemplateGroup()

    tags = {"opfilter":"!!SOP!!", "oprelative":"."}
    spare_in = hou.StringParmTemplate(name=parm_name,
                                      label=parm_label,
                                      num_components=1,
                                      string_type=NodeReference,
                                      tags=tags,
                                      default_value=('',))

    template_grp.addParmTemplate(spare_in)
    node.setParmTemplateGroup(template_grp)

    return node.parm(parm_name)

def block_node_type(node=None):
    ''' Return the type of compile node, if not compile node, return None.
    '''

    if not node:
        return BlockNodeTypes.NONE

    node_type = node.type()

    # not a valid compile node
    if node_type is None \
       or node_type.category().name() != "Sop" \
       or not node_type.name() in ["block_end", "block_begin"]:
        return BlockNodeTypes.NONE

    # check which compil enode it is
    if node_type.name() == "block_end":
        return BlockNodeTypes.COMPILE_END

    method = node.evalParm("method")
    if method == 0:
        return BlockNodeTypes.COMPILE_BEGIN_FEEDBACK
    elif method == 1:
        return BlockNodeTypes.COMPILE_BEGIN_PIECE
    elif method == 2:
        return BlockNodeTypes.COMPILE_BEGIN_METADATA
    elif method == 3:
        return BlockNodeTypes.COMPILE_INPUT
    else:
        return BlockNodeTypes.NONE

def is_compilable_node(node=None):

    if node.verb() is not None:
        return True

    recurs_children = node.glob('*')

    if not recurs_children:
        return False

    for child in recurs_children:
        if len(child.children()) == 0:
            if child.verb() is None:
                return False
    else:
        return True

def get_block_nodes(start_node=None, out_nodes=[], invalid_nodes=[],
                      recursive=True):
    """ Recursively ( or not ) find node from a given node selection,
        either a for loop not begin, or a selection of nodes.
    """

    # on selection only.
    if not recursive:

        if is_compilable_node(node=start_node):
            out_nodes.append(start_node)
            start_node.setColor(hou.Color(0.0, 0.8, 0.0))
        else:
            invalid_nodes.append(start_node)
            start_node.setColor(hou.Color(0.8, 0.0, 0.0))

        return

    # recursive loop, for forloops easy compile.
    cur_nodes = []
    if start_node.type().name() != "block_begin":
        cur_nodes = [n for n in start_node.inputs() if n not in out_nodes \
                     and n not in invalid_nodes \
                     and n.type().name() != "block_end"]

    if start_node.type().name() != "block_end":
        cur_nodes += [n for n in start_node.outputs() if n not in out_nodes \
                      and n not in invalid_nodes \
                      and n.type().name() != "block_end"]

    for cur_in in cur_nodes:

        cur_in_type = cur_in.type().name()

        if (cur_in not in out_nodes or cur_in not in invalid_nodes) and \
            cur_in_type != "block_end":

            if cur_in_type != "block_begin":
                if is_compilable_node(node=cur_in):
                    out_nodes.append(cur_in)
                    cur_in.setColor(hou.Color(0.0, 0.8, 0.0))
                else:
                    invalid_nodes.append(cur_in)
                    cur_in.setColor(hou.Color(0.8, 0.0, 0.0))

            get_block_nodes(start_node=cur_in,
                            out_nodes=out_nodes,
                            invalid_nodes=invalid_nodes)

def extract_expr_token(processed_expr_val=""):

    token_result = []

    # parse expression to find actual node paths
    for token in expression_re.finditer(processed_expr_val):

        span = token.span()
        token_result.append(processed_expr_val[span[0]:span[1]])

    return token_result
    
def replace_expressions(node=None, old_value="", new_value=""):
    ''' Update node's expressions node paths, "old_value" will be replaced
        by "new_value" to basically bind it to a spare input.
    '''
    if not node or old_value == "" or new_value == "":
        return None

    references = node.references()
    if not references:
        return None

    parms = node.parms()

    for parm in parms:

        try:
            expr_val = parm.expression()
        except hou.OperationFailed:
            continue

        processed_expr_val = expr_val.repace(' ', '')
