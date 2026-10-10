from pathlib import Path

import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language as TSLanguage
from tree_sitter import Node, Parser

from src.core.diff_parser import detect_language
from src.models.enums import Language
from src.models.schemas import FunctionNode


class ASTParser:
    """Tree-sitter AST parser extracting FunctionNode objects from polyglot source code."""

    def __init__(self):
        # Initialize Tree-sitter parsers
        self._python_lang = TSLanguage(tree_sitter_python.language())
        self._python_parser = Parser(self._python_lang)

        self._ts_lang = TSLanguage(tree_sitter_typescript.language_typescript())
        self._ts_parser = Parser(self._ts_lang)

    def parse_source(
        self,
        code: str,
        file_path: str,
        language: Language,
    ) -> list[FunctionNode]:
        """Parse source code string into a list of FunctionNode AST representations."""
        code_bytes = code.encode("utf-8")

        if language == Language.PYTHON:
            tree = self._python_parser.parse(code_bytes)
            return self._extract_python_functions(tree.root_node, code_bytes, file_path)
        elif language in (Language.TYPESCRIPT, Language.JAVASCRIPT):
            tree = self._ts_parser.parse(code_bytes)
            return self._extract_typescript_functions(
                tree.root_node, code_bytes, file_path, language
            )
        else:
            return []

    def parse_file(self, file_path: str | Path) -> list[FunctionNode]:
        """Read a file from disk and parse all function nodes."""
        path = Path(file_path)
        lang = detect_language(str(path))
        if not lang:
            return []

        code = path.read_text(encoding="utf-8", errors="replace")
        return self.parse_source(code, str(path), lang)

    def _extract_python_functions(
        self,
        root_node: Node,
        code_bytes: bytes,
        file_path: str,
    ) -> list[FunctionNode]:
        nodes: list[FunctionNode] = []

        def traverse(node: Node, current_class: str | None = None):
            if node.type == "class_definition":
                name_node = node.child_by_field_name("name")
                class_name = (
                    name_node.text.decode("utf-8") if name_node and name_node.text else None
                )
                for child in node.children:
                    traverse(child, class_name)
                return

            if node.type == "function_definition":
                name_node = node.child_by_field_name("name")
                func_name = (
                    name_node.text.decode("utf-8") if name_node and name_node.text else "anonymous"
                )
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                snippet = code_bytes[node.start_byte : node.end_byte].decode(
                    "utf-8", errors="replace"
                )

                nodes.append(
                    FunctionNode(
                        file_path=file_path,
                        function_name=func_name,
                        class_name=current_class,
                        language=Language.PYTHON,
                        start_line=start_line,
                        end_line=end_line,
                        code_snippet=snippet,
                    )
                )

            for child in node.children:
                traverse(child, current_class)

        traverse(root_node)
        return nodes

    def _extract_typescript_functions(
        self,
        root_node: Node,
        code_bytes: bytes,
        file_path: str,
        language: Language,
    ) -> list[FunctionNode]:
        nodes: list[FunctionNode] = []

        def traverse(node: Node, current_class: str | None = None):
            if node.type in ("class_declaration", "class"):
                name_node = node.child_by_field_name("name")
                class_name = (
                    name_node.text.decode("utf-8") if name_node and name_node.text else None
                )
                for child in node.children:
                    traverse(child, class_name)
                return

            if node.type in ("function_declaration", "method_definition"):
                name_node = node.child_by_field_name("name")
                func_name = (
                    name_node.text.decode("utf-8") if name_node and name_node.text else "anonymous"
                )
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                snippet = code_bytes[node.start_byte : node.end_byte].decode(
                    "utf-8", errors="replace"
                )

                nodes.append(
                    FunctionNode(
                        file_path=file_path,
                        function_name=func_name,
                        class_name=current_class,
                        language=language,
                        start_line=start_line,
                        end_line=end_line,
                        code_snippet=snippet,
                    )
                )

            # Arrow function in variable declaration: const foo = () => {}
            elif node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")
                if (
                    value_node
                    and value_node.type in ("arrow_function", "function_expression")
                    and name_node
                ):
                    func_name = name_node.text.decode("utf-8") if name_node.text else "anonymous"
                    start_line = value_node.start_point[0] + 1
                    end_line = value_node.end_point[0] + 1
                    snippet = code_bytes[value_node.start_byte : value_node.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    nodes.append(
                        FunctionNode(
                            file_path=file_path,
                            function_name=func_name,
                            class_name=current_class,
                            language=language,
                            start_line=start_line,
                            end_line=end_line,
                            code_snippet=snippet,
                        )
                    )

            for child in node.children:
                traverse(child, current_class)

        traverse(root_node)
        return nodes
