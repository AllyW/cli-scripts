#!/usr/bin/env python

# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# pylint: disable=line-too-long
import os
import re
import argparse
import json
from enum import Enum
from idlelib.iomenu import encoding
from pathlib import Path
import logging
logger = logging.getLogger(__name__)

class ChangeType(int, Enum):
    DEFAULT = 0
    ADD = 1
    CHANGE = 2
    REMOVE = 3

PathCommandsStr = "Commands"

md_path_pattern = r'\[.*?\]\((.*?\.md)\)'

_COMMAND_INFO_RE = r"# \[Command\] _(?P<group_name>[A-Za-z0-9- ]+)_\n" \
                   r"\n(?P<short_help>(.+\n)+)\n?" \
                   r"(?P<lines_help>\n(^[^#].*\n)+)?" \
                   r"\n## Versions\n" \
                   r"(?P<versions>(\n### \[(?P<version_name>[a-zA-Z0-9-]+)\]\((?P<xml_path>.*)\) \*\*.*\*\*\n" \
                   r"\n(<!-- .* -->\n)+" \
                   r"(?P<examples>\n#### examples\n" \
                   r"(\n- (?P<example_desc>.*)\n" \
                   r"    ```bash\n" \
                   r"(        (?P<example_cmd>.*)\n)+" \
                   r"    ```\n)+)?)+)"
COMMAND_INFO_RE = re.compile(_COMMAND_INFO_RE, re.MULTILINE)
_VERSION_INFO_RE = r"### \[(?P<version_name>[a-zA-Z0-9-]+)\]\((?P<xml_path>.*)\) \*\*(?P<stage>.*)\*\*\n" \
                   r"\n(?P<resources>(<!-- .* -->\n)+)" \
                   r"(?P<examples>\n#### examples\n" \
                   r"(\n- (?P<example_desc>.*)\n" \
                   r"    ```bash\n" \
                   r"(        (?P<example_cmd>.*)\n)+" \
                   r"    ```\n)+)?"
VERSION_INFO_RE = re.compile(_VERSION_INFO_RE, re.MULTILINE)

CTAG = "checked"

# CMDCommand
CMD_PROPERTIES = ["name", "version", "resources", "argGroups", "conditions", "subresourceSelector", "operations", "outputs", "confirmation"]

# CMDResource
RESOURCE_PROPERTIES = ["id", "version", "swagger", "subresource"]


def parse_readme_files(readme_file_path, aaz_root_swagger, cmd_md_files):
    with open(readme_file_path, "r", encoding="utf-8") as file:
        content = file.read()
    md_paths = re.findall(md_path_pattern, content)
    for md_path in md_paths:
        if md_path.lower().endswith('readme.md'):
            parse_readme_files(os.path.join(aaz_root_swagger, "." + md_path), aaz_root_swagger, cmd_md_files)
        else:
            cmd_md_files[md_path] = os.path.join(aaz_root_swagger, "." + md_path)


def parse_cmd_md_file(real_path):
    with open(real_path, "r", encoding="utf-8") as cmd_file:
        info = cmd_file.read()
    command_match = re.match(COMMAND_INFO_RE, info)
    if not command_match:
        print("invalid cmd markdown")
        return None
    cmd_name = command_match.group("group_name").strip()
    max_versions = None
    for version_match in re.finditer(VERSION_INFO_RE, info):
        xml_path = version_match.group("xml_path")
        json_path = str(xml_path).replace(".xml", ".json")
        version_name = version_match.group("version_name")
        # print("version json: ", json_path)
        # print("version name: ", version_name)
        if max_versions is None:
            max_versions = {
                "version_name": version_name,
                "json": json_path
            }
        elif version_name > max_versions["version_name"]:
            max_versions = {
                "version_name": version_name,
                "json": json_path
            }
    return cmd_name, max_versions["version_name"], max_versions["json"]


def parse_cmd_basic_infos(cmd_md_files_from_swagger, cmd_md_files_from_tsp):
    cmd_cmp_json_files = {}
    for relate_path, real_path in cmd_md_files_from_swagger.items():
        if relate_path not in cmd_md_files_from_tsp:
            print("please check, cmd basic md lost in tsp path: ", real_path)
            continue
        tsp_cmd_real_path = cmd_md_files_from_tsp[relate_path]
        cmd_name_s, version_s, json_path_s = parse_cmd_md_file(real_path)
        cmd_name_t, version_t, json_path_t = parse_cmd_md_file(tsp_cmd_real_path)
        if cmd_name_s != cmd_name_t:
            print("tsp cmd {} does not equal swagger cmd {}".format(cmd_name_t, cmd_name_s))
            continue
        if version_s != version_t:
            print("tsp version {} does not equal swagger version {} for cmd {}".format(version_t, version_s, cmd_name_s))
            continue
        if json_path_s != json_path_t:
            print("tsp json {} does not equal swagger json {} for cmd {}".format(json_path_t, json_path_s, cmd_name_s))
            continue
        cmd_cmp_json_files[cmd_name_s] = json_path_t
        # break
    return cmd_cmp_json_files


def compare_resources(resources_swagger, resources_tsp, ckey, hkey, cmd_diffs):
    resources_swagger.sort(key=lambda x: x["id"])
    resources_tsp.sort(key=lambda x: x["id"])
    for resource in resources_swagger:
        rid = resource["id"]
        tckey = ckey + [rid]
        thkey = hkey + ["resource: " + rid]
        if rid not in [item["id"] for item in resources_tsp]:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE))
            continue
        filtered_resource_tsp = [item for item in resources_tsp if item["id"] == rid]
        assert len(filtered_resource_tsp) == 1
        resource_tsp = filtered_resource_tsp[0]
        resource_tsp[CTAG] = True
        for prop in RESOURCE_PROPERTIES:
            if prop not in resource and prop not in resource_tsp:
                continue
            if resource.get(prop, "") != resource_tsp.get(prop, ""):
                cmd_diffs.append((ckey + [prop], hkey + ["prop: " + prop], ChangeType.CHANGE, resource.get(prop, ""), resource_tsp.get(prop, "")))
    for resource in resources_tsp:
        if resource.get(CTAG, None):
            continue
        resource[CTAG] = True
        rid = resource["id"]
        tckey = ckey + [rid]
        thkey = hkey + ["resource: " + rid]
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def compare_args(args_swagger, args_tsp, ckey, hkey, cmd_diffs):
    # use var to identify the args in arg group
    # todo: arg group might have subclass in args, now in arg level, refined as needed
    #
    args_swagger.sort(key=lambda x: x["var"])
    args_tsp.sort(key=lambda x: x["var"])
    for arg in args_swagger:
        var = arg["var"]
        tckey = ckey + [var]
        thkey = hkey + ["arg: " + var]
        if var not in [item["var"] for item in args_tsp]:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE))
            continue
        filtered_arg_tsp = [item for item in args_tsp if item["var"] == var]
        assert len(filtered_arg_tsp) == 1
        arg_tsp = filtered_arg_tsp[0]
        for prop in arg.keys():
            if prop not in arg_tsp:
                cmd_diffs.append((tckey + [prop], thkey + ["prop: " + prop], ChangeType.REMOVE, json.dumps(arg.get(prop, "")), json.dumps(arg_tsp.get(prop, ""))))
                continue
            if arg.get(prop, "") != arg_tsp.get(prop, ""):
                cmd_diffs.append((tckey + [prop], thkey + ["prop: " + prop], ChangeType.CHANGE, json.dumps(arg.get(prop, "")), json.dumps(arg_tsp.get(prop, ""))))
        for prop in (arg_tsp.keys() - arg.keys()):
            cmd_diffs.append((tckey + [prop], thkey + ["prop: " + prop], ChangeType.ADD, json.dumps(arg.get(prop, "")), json.dumps(arg_tsp.get(prop, ""))))
        arg_tsp[CTAG] = True

    for arg in args_tsp:
        if arg.get(CTAG, None):
            continue
        arg[CTAG] = True
        var = arg["var"]
        tckey = ckey + [var]
        thkey = hkey + ["arg: " + var]
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def compare_arg_groups(arg_groups_swagger, arg_groups_tsp, ckey, hkey, cmd_diffs):
    # compare arg_groups in recursive level
    # use name to identify the arg_groups object, another prop in args,
    arg_groups_swagger.sort(key=lambda x: x["name"])
    arg_groups_tsp.sort(key=lambda x: x["name"])
    for arg_group in arg_groups_swagger:
        arg_group_name = arg_group.get("name", "-") # default arg group does not have name, use -
        tckey = ckey + [arg_group_name]
        thkey = hkey + ["argGroup: " + arg_group_name]
        if arg_group_name not in [item.get("name", "-") for item in arg_groups_tsp]:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE))
            continue
        filtered_arg_group_tsp = [item for item in arg_groups_tsp if item.get("name", "-") == arg_group_name]
        assert len(filtered_arg_group_tsp) == 1
        arg_group_tsp = filtered_arg_group_tsp[0]
        arg_group_tsp[CTAG] = True
        compare_args(arg_group.get("args", []), arg_group_tsp.get("args", []), tckey, thkey, cmd_diffs)

    for arg_group in arg_groups_tsp:
        if arg_group.get(CTAG, None):
            continue
        arg_group[CTAG] = True
        arg_group_name = arg_group.get("name", "-") # default arg group does not have name, use -
        tckey = ckey + [arg_group_name]
        thkey = hkey + ["argGroup: " + arg_group_name]
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def compare_conditions(conditions_swagger, conditions_tsp, ckey, hkey, cmd_diffs):
    # compare conditions in item level, not prop level
    # use var to identify the condition object
    conditions_swagger.sort(key=lambda x: x["var"])
    conditions_tsp.sort(key=lambda x: x["var"])
    for condition in conditions_swagger:
        diff_key = condition["var"]
        tckey = ckey + [diff_key]
        thkey = hkey + ["condition var: " + diff_key]
        if diff_key not in [item["var"] for item in conditions_tsp]:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE))
            continue
        filtered_consition_tsp = [item for item in conditions_tsp if item["var"] == diff_key]
        assert len(filtered_consition_tsp) == 1
        condition_tsp = filtered_consition_tsp[0]
        condition_tsp[CTAG] = True
        if condition_tsp != condition:
            cmd_diffs.append((tckey, thkey, ChangeType.CHANGE, json.dumps(condition), json.dumps(condition_tsp)))

    for condition in conditions_tsp:
        if condition.get(CTAG, None):
            continue
        condition[CTAG] = True
        diff_key = condition["var"]
        tckey = ckey + [diff_key]
        thkey = hkey + ["condition var: " + diff_key]
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def compare_operation_http_request_path_args(request_args_swagger, request_args_tsp, ckey, hkey, cmd_diffs):
    # CMDHttpRequestArgs, params and consts, list of  CMDSchemaField, no poly
    request_args_swagger.sort(key=lambda x: x["name"])
    request_args_tsp.sort(key=lambda x: x["name"])
    for arg in request_args_swagger:
        name = arg["name"]
        tckey = ckey + [name]
        thkey = hkey + ["arg: " + name]
        if name not in [item["name"] for item in request_args_tsp]:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE))
            continue
        filtered_arg_tsp = [item for item in request_args_tsp if item["name"] == name]
        assert len(filtered_arg_tsp) == 1
        arg_tsp = filtered_arg_tsp[0]
        for prop in arg.keys():
            if prop not in arg_tsp:
                cmd_diffs.append((tckey + [prop], thkey + ["prop: " + prop], ChangeType.REMOVE, json.dumps(arg.get(prop, "")), json.dumps(arg_tsp.get(prop, ""))))
                continue
            if arg.get(prop, "") != arg_tsp.get(prop, ""):
                cmd_diffs.append((tckey + [prop], thkey + ["prop: " + prop], ChangeType.CHANGE, json.dumps(arg.get(prop, "")), json.dumps(arg_tsp.get(prop, ""))))
        for prop in (arg_tsp.keys() - arg.keys()):
            cmd_diffs.append((tckey + [prop], thkey + ["prop: " + prop], ChangeType.ADD, json.dumps(arg.get(prop, "")), json.dumps(arg_tsp.get(prop, ""))))
        arg_tsp[CTAG] = True

    for arg in request_args_tsp:
        if arg.get(CTAG, None):
            continue
        arg[CTAG] = True
        var = arg["name"]
        tckey = ckey + [var]
        thkey = hkey + ["arg: " + var]
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def compare_operation_http_request_path(request_path_swagger, request_path_tsp, ckey, hkey, cmd_diffs):
    # request path, query, header have same base: params, consts, from CMDHttpRequestArgs
    # header has one more prop: clientRequestId, string but never see before
    # const and params are the same structure
    if request_path_swagger.get("clientRequestId", "") != request_path_tsp.get("clientRequestId", ""):
        tup = (ckey + ["clientRequestId"], hkey + ["clientRequestId"], ChangeType.CHANGE, request_path_swagger["clientRequestId"], request_path_tsp["clientRequestId"])
        cmd_diffs.append(tup)
    compare_operation_http_request_path_args(request_path_swagger.get("params", []), request_path_tsp.get("params", []), ckey + ["params"], hkey + ["params"], cmd_diffs)
    compare_operation_http_request_path_args(request_path_swagger.get("consts", []), request_path_tsp.get("consts", []), ckey + ["consts"], hkey + ["consts"], cmd_diffs)


def compare_operation_http_request_body(request_body_swagger, request_body_tsp, ckey, hkey, cmd_diffs):
    if "json" not in request_body_swagger or "json" not in request_body_tsp:
        logger.error("lost json key in: %s", "->".join(hkey))
        return
    json_swg = request_body_swagger["json"]
    json_tsp = request_body_tsp["json"]
    if json_swg.get("schema", {}) or json_tsp.get("schema", {}):
        compare_cmd_schema(json_swg.get("schema", {}), json_tsp.get("schema", {}), ckey + ["schema"], hkey + ["schema"], cmd_diffs)
        del json_swg["schema"]
        del json_tsp["schema"]
    if json_swg != json_tsp:
        tup = (ckey + ["json"], hkey + ["json"], ChangeType.CHANGE, json.dumps(json_swg), json.dumps(json_tsp))
        cmd_diffs.append(tup)


def compare_operation_http_request(request_swagger, request_tsp, ckey, hkey, cmd_diffs):
    # CMDHttpRequest, not poly
    # prop: [method, path, query, header, body], method required, body is deep in cmdschema format
    if request_swagger["method"] != request_tsp["method"]:
        tup = (ckey + ["method"], hkey + ["method"], ChangeType.CHANGE, request_swagger["method"], request_tsp["method"])
        cmd_diffs.append(tup)
    if request_swagger.get("path", {}) or request_tsp.get("path", {}):
        compare_operation_http_request_path(request_swagger.get("path", {}), request_tsp.get("path", {}), ckey + ["path"], hkey + ["path"], cmd_diffs)
    if request_swagger.get("query", {}) or request_tsp.get("query", {}):
        compare_operation_http_request_path(request_swagger.get("query", {}), request_tsp.get("query", {}), ckey + ["query"], hkey + ["query"], cmd_diffs)
    if request_swagger.get("header", {}) or request_tsp.get("header", {}):
        compare_operation_http_request_path(request_swagger.get("header", {}), request_tsp.get("header", {}), ckey + ["header"], hkey + ["header"], cmd_diffs)
    if request_swagger.get("body", {}) or request_tsp.get("body", {}):
        compare_operation_http_request_body(request_swagger.get("body", {}), request_tsp.get("body", {}), ckey + ["body"], hkey + ["body"], cmd_diffs)


def sort_response(response):
    # CMDHttpResponse
    # statusCode, isError, description, header(dict), body(poly CMDHttpResponseBody)
    if response.get("isError", False):
        return 100
    else:
        return response.get("statusCode", [600])[0]


def find_target_response(response, responses_target):
    isError = response.get("isError", False)
    statusCode = response.get("statusCode", [])
    for resp in responses_target:
        if isError and resp.get("isError", False):
            return resp
        if not isError and statusCode == resp.get("statusCode", []):
            return resp
    return None


def compare_response_props(props_swagger, props_tsp, ckey, hkey, cmd_diffs):
    props_swagger.sort(key=lambda x: x['name'])
    props_tsp.sort(key=lambda x: x['name'])
    for prop in props_swagger:
        name = prop["name"]
        tckey = ckey + [name]
        thkey = hkey + [name]
        if name not in [item["name"] for item in props_tsp]:
            tup = (tckey, thkey, ChangeType.REMOVE, json.dumps(prop))
            cmd_diffs.append(tup)
            continue
        filtered_prop_tsp = [item for item in props_tsp if item["name"] == name]
        assert len(filtered_prop_tsp) == 1
        prop_tsp = filtered_prop_tsp[0]
        compare_cmd_schema(prop, prop_tsp, tckey, thkey, cmd_diffs)
        prop_tsp[CTAG] = True

    for prop in props_tsp:
        if prop.get(CTAG, None):
            continue
        name = prop["name"]
        tckey = ckey + [name]
        thkey = hkey + [name]
        cmd_diffs.append(tckey, thkey, ChangeType.ADD, json.dumps(prop))
        prop[CTAG] = True


def compare_response_additional_props(add_props_swagger, add_props_tsp, ckey, hkey, cmd_diffs):
    other_keys = (set(add_props_swagger.keys()) | set(add_props_tsp.keys())) - {"item"}
    for key in other_keys:
        tckey = ckey + [key]
        thkey = hkey + [key]
        if key not in add_props_swagger and key not in add_props_tsp:
            continue
        elif key in add_props_swagger and key not in add_props_tsp:
            tup = (tckey, thkey, ChangeType.REMOVE, json.dumps(add_props_swagger[key]))
            cmd_diffs.append(tup)
        elif key not in add_props_swagger and key in add_props_tsp:
            tup = (tckey, thkey, ChangeType.ADD, json.dumps(add_props_tsp[key]))
            cmd_diffs.append(tup)
        elif add_props_swagger[key] != add_props_tsp[key]:
            tup = (tckey, thkey, ChangeType.CHANGE, json.dumps(add_props_swagger[key]), json.dumps(add_props_tsp[key]))
            cmd_diffs.append(tup)
    item_swagger = add_props_swagger.get("item", {})
    item_tsp = add_props_tsp.get("item", {})
    if item_swagger or item_tsp:
        compare_cmd_schema(item_swagger, item_tsp, ckey + ["item"], hkey + ["item"], cmd_diffs)


def compare_cmd_schema(schema_swagger, schema_tsp, ckey, hkey, cmd_diffs):
    other_keys = (set(schema_swagger.keys()) | set(schema_tsp.keys())) - {"props"} - {"additionalProps"}
    for other_key in other_keys:
        tckey = ckey + [other_key]
        thkey = hkey + [other_key]
        if other_key not in schema_swagger and other_key not in schema_tsp:
            continue
        elif other_key in schema_swagger and other_key not in schema_tsp:
            tup = (tckey, thkey, ChangeType.REMOVE, json.dumps(schema_swagger[other_key]))
            cmd_diffs.append(tup)
        elif other_key not in schema_swagger and other_key in schema_tsp:
            tup = (tckey, thkey, ChangeType.ADD, json.dumps(schema_tsp[other_key]))
            cmd_diffs.append(tup)
        elif schema_swagger[other_key] != schema_tsp[other_key]:
            tup = (tckey, thkey, ChangeType.CHANGE, json.dumps(schema_swagger[other_key]), json.dumps(schema_tsp[other_key]))
            cmd_diffs.append(tup)
    if schema_swagger.get("props", []) or schema_tsp.get("props", []):
        compare_response_props(schema_swagger.get("props", []), schema_tsp.get("props", []), ckey + ["props"], hkey + ["props"], cmd_diffs)
    if schema_swagger.get("additionalProps", {}) or schema_tsp.get("additionalProps", {}):
        compare_response_additional_props(schema_swagger.get("additionalProps", {}), schema_tsp.get("additionalProps", {}), ckey + ["additionalProps"], hkey + ["additionalProps"], cmd_diffs)


def compare_operation_http_response_body(body_swagger, body_tsp, ckey, hkey, cmd_diffs, cls_obj):
    if "json" not in body_swagger or "json" not in body_tsp:
        logger.error("lost json key in: %s", "->".join(hkey))
        return
    json_swg = body_swagger["json"]
    json_tsp = body_tsp["json"]
    assert json_swg["var"] == "$Instance"
    assert json_tsp["var"] == "$Instance"
    # asjust the actual response body json here
    if "cls" in json_swg["schema"]:
        cls_obj[json_swg["schema"]["cls"]] = json_swg["schema"]["props"]
        del json_swg["schema"]["cls"]
    if json_swg["schema"]["type"].find("@") == 0:
        # "json": {
        #    "var": "$Instance",
        #    "schema": {
        #           "type": "@OrganizationResource_read"
        #     }
        #}
        cls_name = json_swg["schema"]["type"][1:]
        if cls_name not in cls_obj:
            logger.error("lost instance cls %s, please check %s", cls_name, "->".join(hkey))
            return
        json_swg["schema"]["type"] = "object"
        json_swg["schema"]["props"] = cls_obj[cls_name]
    compare_cmd_schema(json_swg["schema"], json_tsp["schema"], ckey + ["schema"], hkey + ["schema"], cmd_diffs)


def compare_operation_http_responses(responses_swagger, responses_tsp, ckey, hkey, cmd_diffs, cls_obj):
    # check response by status code, error first
    # statusCodes, isError, description, header, body,
    responses_swagger.sort(key=sort_response)
    responses_tsp.sort(key=sort_response)
    for response in responses_swagger:
        key = "error" if response.get("isError", None) else ".".join([str(x) for x in response.get("statusCode", [])])
        tckey = ckey + [key]
        thkey = hkey + [key]
        response_tsp = find_target_response(response, responses_tsp)
        if response_tsp is None:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE, json.dumps(response)))
            continue
        if response.get("isError", None):
            if response != response_tsp:
                cmd_diffs.append((tckey, thkey, ChangeType.CHANGE, json.dumps(response), json.dumps(response_tsp)))
            continue
        if response.get("description", "") != response_tsp.get("description", ""):
            cmd_diffs.append((tckey + ["description"], thkey + ["description"], ChangeType.CHANGE, response.get("description", ""), response_tsp.get("description", "")))
        if response.get("header", {}) != response_tsp.get("header", {}):
            cmd_diffs.append((tckey + ["header"], thkey + ["header"], ChangeType.CHANGE,
                              json.dumps(response.get("header", {})), json.dumps(response_tsp.get("header", {}))))
        if response.get("body", {}) or response_tsp.get("body", {}):
            compare_operation_http_response_body(response.get("body", {}), response_tsp.get("body", {}), tckey + ["body"], thkey + ["body"], cmd_diffs, cls_obj)


def compare_operation_http(http_swagger, http_tsp, ckey, hkey, cmd_diffs, cls_obj):
    # CMDHttpAction
    # path required, request, response, only these three props
    if http_swagger["path"] != http_tsp["path"]:
        tup = (ckey + ["path"], hkey + ["path"], ChangeType.CHANGE, http_swagger["path"], http_tsp["path"])
        cmd_diffs.append(tup)
    compare_operation_http_request(http_swagger["request"], http_tsp["request"], ckey + ["request"], hkey + ["request"], cmd_diffs)
    compare_operation_http_responses(http_swagger["responses"], http_tsp["responses"], ckey + ["responses"], hkey + ["responses"], cmd_diffs, cls_obj)


def compare_operation(operation_swagger, operation_tsp, ckey, hkey, cmd_diffs, cls_obj):
    com_props = operation_swagger.keys() - {"http"}
    for prop in com_props:
        tckey = ckey + [prop]
        thkey = hkey + ["prop: " + prop]
        if prop not in operation_tsp.keys():
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE, json.dumps(operation_swagger.get(prop, "")), json.dumps(operation_tsp.get(prop, ""))))
        elif operation_swagger.get(prop, "") != operation_tsp.get(prop, ""):
            cmd_diffs.append((tckey, thkey, ChangeType.CHANGE, json.dumps(operation_swagger.get(prop, "")), json.dumps(operation_tsp.get(prop, ""))))

    new_tsp_props = operation_tsp.keys() - operation_swagger.keys() - {"http"}
    for prop in new_tsp_props:
        tckey = ckey + [prop]
        thkey = hkey + ["prop: " + prop]
        cmd_diffs.append((tckey, thkey, ChangeType.ADD, json.dumps(operation_swagger.get(prop, "")),
                          json.dumps(operation_tsp.get(prop, ""))))
    compare_operation_http(operation_swagger["http"], operation_tsp["http"], ckey, hkey, cmd_diffs, cls_obj)


def compare_operations(operations_swagger, operations_tsp, ckey, hkey, cmd_diffs):
    # compare operations in original order, update : get ->update -> create or update
    # use operationId or dict item
    # store cls key across operations responses, get cls response used for update response
    cls_obj = {}
    for i, operation in enumerate(operations_swagger):
        operation_tsp = operations_tsp[i]
        tckey = ckey + [str(i)]
        thkey = hkey + ["operation ind: " + str(i)]
        if "operationId" in operation:
            # key updated in operation cmp inner
            compare_operation(operation, operation_tsp, tckey, thkey, cmd_diffs, cls_obj)
        else:
            if operation != operation_tsp:
                cmd_diffs.append((tckey, thkey, ChangeType.CHANGE, json.dumps(operation), json.dumps(operation_tsp)))
        operation_tsp[CTAG] = True

    for i, operation in enumerate(operations_tsp):
        if operation.get(CTAG, None):
            continue
        operation[CTAG] = True
        diff_key = str(i)
        tckey = ckey + [diff_key]
        thkey = hkey + ["operation ind: " + diff_key]
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def compare_outputs(outputs_swagger, outputs_tsp, ckey, hkey, cmd_diffs):
    # compare outputs in item level, not prop level
    # the output object might be string, array and object type, we use key.join() to sort and compare
    outputs_swagger.sort(key=lambda x: "-".join(sorted(x.keys())))
    outputs_tsp.sort(key=lambda x: "-".join(sorted(x.keys())))
    for output in outputs_swagger:
        diff_key = "-".join(sorted(output.keys()))
        tckey = ckey + [output.get("ref", diff_key)]
        thkey = hkey + ["output ref: " + output.get("ref", diff_key)]
        if diff_key not in ["-".join(sorted(item.keys())) for item in outputs_tsp]:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE))
            continue
        filtered_output_tsp = [item for item in outputs_tsp if "-".join(sorted(item.keys())) == diff_key]
        assert len(filtered_output_tsp) == 1
        output_tsp = filtered_output_tsp[0]
        if output_tsp != output:
            cmd_diffs.append((tckey, thkey, ChangeType.CHANGE, json.dumps(output), json.dumps(output_tsp)))
        output_tsp[CTAG] = True

    for output in outputs_tsp:
        if output.get(CTAG, None):
            continue
        output[CTAG] = True
        diff_key = "-".join(sorted(output.keys()))
        tckey = ckey + [output.get("ref", diff_key)]
        thkey = hkey + ["output ref: " + output.get("ref", diff_key)]
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def diff_command_json(command_swagger, command_tsp, ckey, hkey, cmd_diffs):
    cmd_props = command_swagger.keys()
    new_props = set(cmd_props) - set(CMD_PROPERTIES) - {CTAG}
    if new_props:
        logger.warning("please check cmd level properties: %s from swagger for cmd: %s", ",".join(list(new_props)), command_swagger["name"])
    tsp_new_props = set(command_tsp.keys()) - set(CMD_PROPERTIES) - {CTAG}
    if tsp_new_props:
        logger.warning("please check cmd level properties: %s from tsp for cmd: %s", ",".join(list(tsp_new_props)), command_swagger["name"])

    for prop in ["version", "confirmation"]:
        if prop not in command_swagger and prop not in command_tsp:
            continue
        if command_swagger.get(prop, "") != command_tsp.get(prop, ""):
            cmd_diffs.append((ckey + [prop], hkey + ["prop: " + prop], ChangeType.CHANGE, command_swagger.get(prop, ""), command_tsp.get(prop, "")))
    compare_resources(command_swagger.get("resources", []), command_tsp.get("resources", []), ckey, hkey, cmd_diffs)
    compare_arg_groups(command_swagger.get("argGroups", []), command_tsp.get("argGroups", []), ckey, hkey, cmd_diffs)

    if command_swagger.get("subresourceSelector", {}) != command_tsp.get("subresourceSelector", {}):
        tup = (ckey + ["subresourceSelector"],
               hkey + ["subresourceSelector"],
               ChangeType.CHANGE,
               json.dumps(command_swagger.get("subresourceSelector", {})),
               json.dumps(command_tsp.get("subresourceSelector", {}))
               )
        cmd_diffs.append(tup)

    compare_conditions(command_swagger.get("conditions", []), command_tsp.get("conditions", []), ckey, hkey, cmd_diffs)
    compare_operations(command_swagger.get("operations", []), command_tsp.get("operations", []), ckey, hkey, cmd_diffs)
    compare_outputs(command_swagger.get("outputs", []), command_tsp.get("outputs", []), ckey, hkey, cmd_diffs)


def diff_commands_json(commands_swagger, commands_tsp, ckey, hkey, cmd_diffs):
    commands_swagger.sort(key=lambda x: x['name'])
    commands_tsp.sort(key=lambda x: x['name'])
    for command in commands_swagger:
        cmd_name = command["name"]
        tckey = ckey + [cmd_name]
        thkey = hkey + ["command:" + cmd_name]
        if cmd_name not in [item["name"] for item in commands_tsp]:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE))
            continue
        filtered_command_tsp = [item for item in commands_tsp if item["name"] == cmd_name]
        assert len(filtered_command_tsp) == 1
        command_tsp = filtered_command_tsp[0]
        diff_command_json(command, command_tsp, tckey, thkey, cmd_diffs)
        command_tsp[CTAG] = True

    for command in commands_tsp:
        if command.get(CTAG, None):
            continue
        cmd_name = command["name"]
        tckey = ckey + [cmd_name]
        thkey = hkey + ["command:" + cmd_name]
        command[CTAG] = True
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def diff_commands_groups_json(commands_group_swagger, commands_group_tsp, ckey, hkey, cmd_diffs):
    commands_group_swagger.sort(key=lambda x: x['name'])
    commands_group_tsp.sort(key=lambda x: x['name'])
    for command_group in commands_group_swagger:
        command_group_name = command_group["name"]
        tckey = ckey + [command_group_name]
        thkey = hkey + ["command-group:" + command_group_name]
        if command_group_name not in [item["name"] for item in commands_group_tsp]:
            cmd_diffs.append((tckey, thkey, ChangeType.REMOVE))
            continue
        filtered_command_group_tsp = [item for item in commands_group_tsp if item["name"] == command_group_name]
        assert len(filtered_command_group_tsp) == 1
        command_group_tsp = filtered_command_group_tsp[0]
        diff_commands_json(command_group.get("commands", []), command_group_tsp.get("commands", []), tckey, thkey, cmd_diffs)
        diff_commands_groups_json(command_group.get("commandGroups", []), command_group_tsp.get("commandGroups", []), tckey, thkey, cmd_diffs)
        command_group_tsp[CTAG] = True

    for command_group in commands_group_tsp:
        if command_group.get(CTAG, None):
            continue
        command_group_name = command_group["name"]
        tckey = ckey + [command_group_name]
        thkey = hkey + ["command-group:" + command_group_name]
        command_group[CTAG] = True
        cmd_diffs.append((tckey, thkey, ChangeType.ADD))


def compare_cmd_jsons(cmd, cmd_swagger_json, cmd_tsp_json, cmd_diffs):
    assert cmd_swagger_json["plane"] == cmd_tsp_json["plane"]
    resource_ids_swg = sorted(cmd_swagger_json["resources"], key=lambda x: x['id'])
    resource_ids_tsp = sorted(cmd_tsp_json["resources"], key=lambda x: x['id'])
    diff_search_key = ["root"]
    if resource_ids_swg != resource_ids_tsp:
        cmd_diffs.append((".".join(diff_search_key + ["resources"]), 1))
    diff_commands_groups_json(cmd_swagger_json.get("commandGroups", []), cmd_tsp_json.get("commandGroups", []), [], diff_search_key, cmd_diffs)


def find_target_parent_path(target_path, path_input):
    path = Path(path_input)
    current_path = path
    target_parent_path = None
    while current_path:
        if current_path.name == target_path:
            target_parent_path = current_path.parent
            # print(f"sub '{target_path}' parent: {target_parent_path}")
            break
        current_path = current_path.parent
    else:
        print(f"cannot find '{target_path}'")
    return target_parent_path


def parse_compared_module_jsons(swagger_path, tsp_path, modules):
    aaz_root_swagger = os.path.abspath(find_target_parent_path("Commands", swagger_path))
    aaz_root_tsp = os.path.abspath(find_target_parent_path("Commands", tsp_path))
    # print("aaz_root_swagger:", aaz_root_swagger)
    # print("aaz_root_tsp:", aaz_root_tsp)
    readme_file = Path(aaz_root_swagger) / ("Commands/" + "/".join(modules) + "/readme.md")
    # print("readme file: ", readme_file)
    cmd_md_files_from_swagger = {}
    parse_readme_files(readme_file, aaz_root_swagger, cmd_md_files_from_swagger)
    cmd_md_files_from_tsp = {}
    readme_file = Path(aaz_root_tsp) / ("Commands/" + "/".join(modules) + "/readme.md")
    # print("readme file: ", readme_file)
    parse_readme_files(readme_file, aaz_root_tsp, cmd_md_files_from_tsp)
    cmd_json_files = parse_cmd_basic_infos(cmd_md_files_from_swagger, cmd_md_files_from_tsp)
    cmd_diffs_from_json = {}
    for cmd, json_relate_path in cmd_json_files.items():
        # logger.warning("cmd_name: %s, json file: %s", cmd, json_relate_path)
        cmd_diffs = []
        swagger_json_path = os.path.join(aaz_root_swagger, "." + json_relate_path)
        tsp_json_path = os.path.join(aaz_root_tsp, "." + json_relate_path)
        with open(swagger_json_path, "r", encoding="utf-8") as f:
            cmd_swagger_json = json.load(f)
        with open(tsp_json_path, "r", encoding="utf-8") as f:
            cmd_tsp_json = json.load(f)
        # print("cmd_swagger_json: ", cmd_swagger_json)
        compare_cmd_jsons(cmd, cmd_swagger_json, cmd_tsp_json, cmd_diffs)
        cmd_diffs_from_json[cmd] = cmd_diffs
    # print("cmd_diffs_from_json: ", cmd_diffs_from_json)
    out_arr = []
    for key, diffs_arr in cmd_diffs_from_json.items():
        for diff in diffs_arr:
            item_list = list(diff)
            join_key = ["->".join(item_list[0]), "->".join(item_list[1]), str(item_list[2])] + item_list[3:]
            print(join_key)
            out_arr.append(join_key)
    return out_arr



def main(swagger_path, tsp_path):
    if not os.path.isdir(swagger_path) or not os.path.isdir(tsp_path):
        raise Exception("swagger aaz path and tsp aaz path is required")
    assert swagger_path.find(PathCommandsStr) != -1
    assert tsp_path.find(PathCommandsStr) != -1
    modules = swagger_path[swagger_path.find(PathCommandsStr) + len(PathCommandsStr) + 1:].strip("/").strip("\\").split("/")
    print("modules: ", modules)
    if tsp_path[tsp_path.find(PathCommandsStr) + len(PathCommandsStr) + 1:].strip("/").strip("\\").split("/") != modules:
        raise Exception("swagger aaz module need to be the same as tsp aaz module")
    out_arr = parse_compared_module_jsons(swagger_path, tsp_path, modules)
    file_name = "-".join([module.replace("\\", "-") for module in modules]) + ".csv"
    import csv
    with open(file_name, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file, delimiter='\t')
        writer.writerows(out_arr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpas", "--rp-aaz-folder-from-swagger",
                        # required=True,
                        default="..\\aaz\\Commands\monitor\\",
                        help="the resource provider's aaz model folder generated from swagger")
    parser.add_argument("--rpat", "--rp-aaz-folder-from-tsp",
                        # required=True,
                        default="..\\aaz\\Commands\monitor\\",
                        help="the resource provider's aaz model folder generated from tsp")
    args = parser.parse_args()
    print(vars(args))
    main(args.rpas, args.rpat)