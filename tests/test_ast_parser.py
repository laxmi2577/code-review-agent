from src.core.ast_parser import ASTParser
from src.models.enums import Language

PYTHON_CODE = """class UserService:
    def __init__(self, db):
        self.db = db

    def get_user_by_id(self, user_id: int):
        return self.db.find(user_id)

def standalone_helper(x: int) -> int:
    return x * 2
"""

TYPESCRIPT_CODE = """class AuthService {
    login(token: string): boolean {
        return token.length > 0;
    }
}

function verifyToken(secret: string): void {
    console.log(secret);
}

const formatUser = (user: any) => {
    return user.name;
};
"""


def test_parse_python_functions_and_methods():
    parser = ASTParser()
    nodes = parser.parse_source(PYTHON_CODE, "src/user_service.py", Language.PYTHON)

    assert len(nodes) == 3
    func_names = [n.function_name for n in nodes]
    assert "__init__" in func_names
    assert "get_user_by_id" in func_names
    assert "standalone_helper" in func_names

    method_node = next(n for n in nodes if n.function_name == "get_user_by_id")
    assert method_node.class_name == "UserService"
    assert method_node.language == Language.PYTHON
    assert method_node.start_line == 5
    assert method_node.end_line == 6

    standalone_node = next(n for n in nodes if n.function_name == "standalone_helper")
    assert standalone_node.class_name is None
    assert standalone_node.start_line == 8
    assert standalone_node.end_line == 9


def test_parse_typescript_functions_and_methods():
    parser = ASTParser()
    nodes = parser.parse_source(TYPESCRIPT_CODE, "src/auth.ts", Language.TYPESCRIPT)

    assert len(nodes) == 3
    func_names = [n.function_name for n in nodes]
    assert "login" in func_names
    assert "verifyToken" in func_names
    assert "formatUser" in func_names

    method_node = next(n for n in nodes if n.function_name == "login")
    assert method_node.class_name == "AuthService"
    assert method_node.language == Language.TYPESCRIPT


def test_parse_empty_or_unsupported():
    parser = ASTParser()
    nodes = parser.parse_source("SELECT * FROM users;", "query.sql", Language.GO)
    assert nodes == []
