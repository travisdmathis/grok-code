"""Multi-lang editing with tree-sitter AST."""

from tree_sitter import Language, Parser, Node
from tree_sitter_languages import get_language, get_parser  # pip tree-sitter-languages
from pathlib import Path
from .base import Tool
from .file_ops import has_file_been_read

LANGUAGES = {
    'py': get_language('python'),
    'js': get_language('javascript'),
    'ts': get_language('typescript'), 
    'cpp': get_language('cpp'),
    'c_sharp': get_language('csharp'),
    'rust': get_language('rust'),
    # Add more
}

def detect_lang(path: Path) -> str:
    suffix = path.suffix[1:]
    mapping = {'py': 'py', 'js': 'js', 'ts': 'ts', 'cpp': 'cpp', 'cs': 'c_sharp', 'rs': 'rust'}
    return mapping.get(suffix, 'unknown')

class TreeEditTool(Tool):
    name = "tree_edit"
    description = \"\"\"Multi-lang AST edit with tree-sitter (py/js/ts/cpp/c#/rust).

Instructions: 'insert func after import', 'replace class Foo body with ...'.
Query-based node ops.
Requires read_file first.
    \"\"\"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "lang": {"type": "string", "enum": list(LANGUAGES), "default": "auto"},
                "instructions": {"type": "string"},
            },
            "required": ["file_path", "instructions"],
        }

    async def execute(self, file_path: str, instructions: str, lang: str = "auto") -> str:
        path = Path(file_path)
        if not has_file_been_read(str(path)):
            return "Read file first."
        content_bytes = path.read_bytes()
        suffix_lang = detect_lang(path)
        lang = suffix_lang if lang == "auto" else lang
        if lang not in LANGUAGES:
            return f"Unsupported lang: {lang}"
        LANGUAGE = LANGUAGES[lang]
        parser = Parser()
        parser.set_language(LANGUAGE)
        tree = parser.parse(content_bytes)
        root = tree.root_node

        # Simple ops from instructions
        if 'insert' in instructions:
            # Find target node, insert sibling text
            target_query = "(function_definition name: (_) @target)"  # Extend
            query = LANGUAGE.query(target_query)
            matches = query.captures(root)
            if matches:
                target_node = matches[0][0]
                insert_text = parse_insert_text(instructions)
                # Serialize insert as node
                new_bytes = insert_text.encode()
                new_tree = parser.parse(new_bytes)
                insert_node = new_tree.root_node.children[0]
                # Parent replace children slice
                parent = target_node.parent
                idx = list(parent.children).index(target_node)
                new_children = parent.children[:idx+1] + (insert_node,) + parent.children[idx+1:]
                new_root = parent.replace(new_children)
                new_content = new_root.sexp()  # Serialize? Use byte slice edit
                # Simple: string insert at end_node.end_byte
                insert_pos = target_node.end_byte
                new_content = content_bytes[:insert_pos] + new_bytes + content_bytes[insert_pos:]
            else:
                new_content = content_bytes + b'\n' + parse_insert_text(instructions).encode()
        elif 'replace' in instructions:
            # Query replace node text
            pass  # Similar
        else:
            return "Unsupported instr."

        path.write_bytes(new_content)
        return f"Tree-edit {lang} {path}: applied {instructions}"

def parse_insert_text(instr: str) -> str:
    # Stub: extract code from "insert def foo(): pass"
    return instr.split('insert ')[1] if 'insert ' in instr else "pass"

# Extend with queries per lang/op