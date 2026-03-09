# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any, Dict, List, Optional


def dict_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """merge two dict recursively and return a new merged dict
    1. if two nodes in the same position are both dicts,
       merge is recursively,
    2. if two nodes in the same position are not both dicts,
       value from the second one overwrites one in first.

    Args:
        a (dict): first dict
        b (dict): second dict

    Returns:
        dict: a new merged dict
    """
    merged = dict()
    for k in set(a.keys()).union(b.keys()):
        if (k in a) and (k in b):
            if isinstance(a[k], dict) and isinstance(b[k], dict):
                merged[k] = dict_merge(a[k], b[k])
            else:
                merged[k] = b[k]
        elif k in a:
            merged[k] = a[k]
        else:  # k in b
            merged[k] = b[k]
    return merged


def list_item_merge(
    a: List[Dict[str, Any]], b: List[Dict[str, Any]], unique_key: Optional[str]
) -> List[Dict[str, Any]]:
    """
    merge two list items into a new one
    will use unique_key to identify the item
    """
    if not unique_key:
        return a + b

    merged = []
    unique_dict = {bb.get(unique_key, ""): bb for bb in b}
    for item in a:
        if item.get(unique_key, "") not in unique_dict.keys():
            merged.append(item)

    merged += b

    return merged
