# MIT License
# 
# Copyright (c) 2017 Guillaume Jobst, www.cgtoolbox.com
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

import hou
import sys
import os
import re

__version__ = "0.5.0"

NodeReference = hou.stringParmType.NodeReference
COMPILE_NODE_COLOR = hou.Color(0.75, 0.75, 0.0)

expression_re = re.compile('\"\.\./(.*?)\"|\"(/obj/)(.*?)\"|\"(obj/)(.*?)\"')

class ResultSummary(object):

    __slots__ = ["compile_blocks_created",
                 "parm_updated"]

    def __init__(self):

        self.compile_blocks_created = []
        self.parm_updated = {}

    def __str__(self):

        details = "Compile block created:\n"
        for n in self.compile_blocks_created:
            details += '\n    -' + n.name()
        details += "\n\nParameters updated:"

        for k, v in self.parm_updated.iteritems():
            details += "\n\n    Node: " + k
            for n in v:
                details += '\n        -' + n

        return details

# ---------------- Menu methods
def compile_selection():

    out_nodes = []
    invalid_nodes = []

    summary = ResultSummary()

    # check for invalid nodes ( not compilable )
    if invalid_nodes:

        details_str = '\n'.join([n.name() for n in invalid_nodes])

        hou.ui.displayMessage(("Can't compile the forloop "
                               "as non-compilable nodes were found"),
                                title="Error",
                                details=details_str,
                                details_label="Show non-compilable nodes",
                                severity=hou.severityType.Error)
        return None

    result = get_start_end_nodes()
    if not result:
        return None

    start_node, end_node = result

    for n in hou.selectedNodes():
      get_block_nodes(start_node=n,
                      out_nodes=out_nodes,
                      invalid_nodes=invalid_nodes,
                      recursive=False)

    # create compile block
    block_name = "compile_" + start_node.name()
    compile_begin = insert_compile_block(node=start_node,
                                         block_name=block_name)
    compile_end = insert_compile_block(node=end_node,
                                       block_type="compile_end",
                                       block_name=block_name)

    compile_begin.parm("blockpath").set("../" + compile_end.name())

    summary.compile_blocks_created = [compile_begin, compile_end]

    # update node references and add spare input if needed
    for n in out_nodes:
        parms_updated = update_node_references(node=n)
        if parms_updated is not None:
            summary.parm_updated[n.name()] = parms_updated

    compile_end.setDisplayFlag(True)
    compile_end.setRenderFlag(True)
    compile_end.setCurrent(True)

    hou.ui.displayMessage("Compilation done !",
                          title="Success",
                          details=str(summary),
                          details_label="Show more infos")
    
def compile_forloop(node=None):

    summary = ResultSummary()

    out_nodes = []
    invalid_nodes = []

    get_block_nodes(start_node=node,
                    out_nodes=out_nodes,
                    invalid_nodes=invalid_nodes)

    # check for invalid nodes ( not compilable )
    if invalid_nodes:

        details_str = '\n'.join([n.name() for n in invalid_nodes])

        hou.ui.displayMessage(("Can't compile the forloop "
                               "as non-compilable nodes were found"),
                                title="Error",
                                details=details_str,
                                details_label="Show non-compilable nodes",
                                severity=hou.severityType.Error)
        return

    forloop_nodes = [n for n in node.dependents() \
                     if n.type().name() in ["block_begin", "block_end"] \
                     and n.evalParm("method") != 2]
    forloop_nodes.append(node)

    block_name = "compile_" + node.name()
    expression_value = ""
    compile_block_nodes = []

    # create compile block nodes
    for n in forloop_nodes:

        if n.type().name() == "block_end":
            block_type="compile_end"
        else:
            block_type="compile_begin"

        n = insert_compile_block(node=n, block_type=block_type,
                                 block_name=block_name)

        if block_type == "compile_end":
            expression_value = "../" + n.name()

        compile_block_nodes.append(n)

    summary.compile_blocks_created = compile_block_nodes

    # update compile block start expression
    for n in compile_block_nodes:

        if n is not None and n.type().name() != "compile_begin":
            continue

        n.parm("blockpath").set(expression_value)

    # switch on multithreading for loop
    node.parm("multithread").set(1)

    # update node references and add spare input if needed
    for n in out_nodes:
        parms_updated = update_node_references(node=n)
        if parms_updated is not None:
            summary.parm_updated[n.name()] = parms_updated

    hou.ui.displayMessage("Compilation done !",
                          title="Success",
                          details=str(summary),
                          details_label="Show more infos")

def update_selected_node(node=None):

    summary = ResultSummary()

    parms_updated = update_node_references(node=node)
    if parms_updated is not None:
        summary.parm_updated[node.name()] = parms_updated

    hou.ui.displayMessage("Update done !",
                          title="Success",
                          details=str(summary),
                          details_label="Show more infos")

def is_valid_forloop_compilation(node=None):

    outputs = node.outputs()

    if outputs:
        already_cmp = any([n.type().name() == "compile_end" for \
                           n in outputs])
    else:
        already_cmp = False
    
    return node.type().name() == "block_end" and not already_cmp

def is_valid_for_node_update(node=None):

    tokens = []
    for parm in node.parms():

        is_expr = True
        try:
            expr = parm.expression()
        except hou.OperationFailed:
            is_expr = False
            expr = parm.rawValue()

        token = extract_expr_token(node=node,
                                   processed_expr_val=expr)
        if token:
            tokens += token

    return len(tokens) > 0

# ----------------

def insert_compile_block(node=None, block_type="compile_begin",
                         block_name=""):

    input_node = node.inputs()
    outputs = node.outputConnections()

    if not input_node:
        return None
    
    node_pos = node.position()

    input_node = input_node[0]

    parent = node.parent()
    comp = parent.createNode(block_type,
                             node_name=block_name)
    comp.setColor(COMPILE_NODE_COLOR)

    if block_type == "compile_begin":
        comp.setInput(0, input_node)
        node.setInput(0, comp)

        comp_pos = node_pos + hou.Vector2([0.0, 1.0])
        comp.setPosition(comp_pos)

    else:
        comp.setInput(0, node)
        comp_pos = node_pos + hou.Vector2([0.0, -1.0])
        comp.setPosition(comp_pos)

        for c in outputs:

            out = c.outputItem()
            out.setInput(c.outputIndex(), comp)

        comp.setDisplayFlag(True)
        comp.setRenderFlag(True)
        comp.setCurrent(True)

    return comp

def add_spare_input(node=None, index=0, value=""):

    parm_name = "spare_input{}".format(index)
    parm_label = "Spare Input {}".format(index)

    if node.parm(parm_name) is not None:
        return node.parm(parm_name)

    template_grp = node.parmTemplateGroup()

    tags = {"opfilter":"!!SOP!!", "oprelative":"."}
    help = ('Refer to this in expressions as -{0},'
            ' such as: npoint(-{0})'.format(index))

    spare_in = hou.StringParmTemplate(name=parm_name,
                                      label=parm_label,
                                      num_components=1,
                                      string_type=NodeReference,
                                      tags=tags,
                                      default_value=('',),
                                      help=help)

    template_grp.addParmTemplate(spare_in)
    node.setParmTemplateGroup(template_grp)

    node.parm(parm_name).set(value.replace('"', ''))

    return node.parm(parm_name)

def get_spare_input(node=None, value=""):

    spare_inputs = [p for p in node.parms() \
                    if p.name().startswith("spare_input") and \
                    p.eval() == value]

    if not spare_inputs:
        return None

    return spare_inputs[0]

def get_n_spare_inputs(node=None):

    spare_inputs = [p for p in node.parms() \
                    if p.name().startswith("spare_input")]

    return len(spare_inputs)

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
        else:
            invalid_nodes.append(start_node)

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
                else:
                    invalid_nodes.append(cur_in)

            get_block_nodes(start_node=cur_in,
                            out_nodes=out_nodes,
                            invalid_nodes=invalid_nodes)

def update_node_references(node=None):
    """ Update node parameters expression if needed, to update node references
        to use spare input created instread.
    """
    parms = node.parms()

    parm_changed = []

    for parm in parms:

        is_expr = True
        try:
            expr = parm.expression()
        except hou.OperationFailed:
            is_expr = False
            expr = parm.rawValue()

        token = extract_expr_token(node=node,
                                    processed_expr_val=expr)
        if not token:
            continue

        old_values = []
        new_values = []

        for t in token:
            spare_input = get_spare_input(node=node,
                                          value=t.replace('"', ''))
            if not spare_input:
                idx = get_n_spare_inputs(node=node)
                spare_input = add_spare_input(node=node,
                                              index=idx,
                                              value=t)
            else:
                idx = int(spare_input.name().split('input')[-1])

            old_values.append(t)
            new_values.append(t.replace(t, '-{}'.format(idx + 1)))

        for old_v, new_v in zip(old_values, new_values):

            expr = expr.replace(old_v, new_v)

        if is_expr:
            parm.setExpression(expr)
        else:
            parm.set(expr)

        parm_changed.append(parm.name())

    if not parm_changed:
        return None

    return parm_changed

def extract_expr_token(node=None, processed_expr_val=""):

    token_result = []

    # parse expression to find actual node paths
    for token in expression_re.finditer(processed_expr_val):

        span = token.span()
        s = processed_expr_val[span[0]:span[1]]
        s = s.replace(',', '').replace(' ', '').replace('"', '')

        n = node.node(s)
        if isinstance(n, hou.Node):
            token_result.append('"' + s + '"')

    return token_result
    
def replace_expressions(parm=None, old_values=[], new_values=[]):
    
    if not node or old_value == "" or new_value == "":
        return None

    references = node.references()
    if not references:
        return None

    try:
        expr_val = parm.expression()
    except hou.OperationFailed:
        return None

    processed_expr_val = expr_val.repace(' ', '')

    return parm

def get_start_end_nodes(nodes=hou.selectedNodes()):

    if len(nodes) < 2:
        hou.ui.displayMessage("Need to select more than one node",
                              severity=hou.severityType.Error)
        return None

    start_node = None
    end_node = None

    for node in nodes:

        if start_node is not None and end_node is not None:
            break

        if all([n not in nodes for n in node.outputs()]):
            end_node = node
            continue

        if all([n not in nodes for n in node.inputs()]):
            start_node = node
            continue

    return start_node, end_node
