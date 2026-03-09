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

from typing import List

from langchain_core.output_parsers import BaseTransformOutputParser


class RagIntentMessageChunkOutputParser(BaseTransformOutputParser[bool]):
    """OutputParser that parses BaseMessageChunk into intent of whether to search."""

    @classmethod
    def is_lc_serializable(cls) -> bool:
        """Return whether this class is serializable."""
        return True

    @property
    def _type(self) -> str:
        """Return the output parser type for serialization."""
        return "default"

    def parse(self, text: str) -> bool:
        """Parse the output of the resource_id into a bool.

        Args:
            text (str): The output of the resource_id.

        Returns:
            Tuple(bool, str): The bool indicating whether to search.
                True, return empty str
                False, return direct answer
        """
        if "无需检索" in text:
            return False
        return True


class RagRewriteMessageChunkOutputParser(BaseTransformOutputParser[str]):
    """OutputParser that parses BaseMessageChunk into intent of whether to search."""

    @classmethod
    def is_lc_serializable(cls) -> bool:
        """Return whether this class is serializable."""
        return True

    @property
    def _type(self) -> str:
        """Return the output parser type for serialization."""
        return "default"

    def parse(self, text: str) -> str:
        """Parse the output of the resource_id into a bool."""
        return text.strip()


class RagRewriteOutputParser(BaseTransformOutputParser[List[str]]):
    """Parse llm output to List[str]"""

    def parse(self, text: str) -> List[str]:
        queries = text.split("\n")
        # filter extreme shot query
        return [q.strip() for q in queries if len(q) > 3]
