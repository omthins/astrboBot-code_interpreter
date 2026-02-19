"""
代码执行沙箱模块
提供安全的Python代码执行环境
"""

import ast
import subprocess
import sys
import os
import tempfile
import shutil
import time
import json
import re
from typing import Optional, Tuple, List, Any, Dict
from dataclasses import dataclass, field
from pathlib import Path
import traceback

from .library_manager import LibraryManager


@dataclass
class ExecutionResult:
    """代码执行结果"""
    success: bool
    stdout: str
    stderr: str
    return_value: Any = None
    execution_time: float = 0.0
    generated_files: List[str] = field(default_factory=list)
    generated_images: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    installed_libraries: List[str] = field(default_factory=list)


class CodeValidator:
    """代码验证器，检查代码安全性"""

    DANGEROUS_FUNCTIONS = {
        'eval', 'exec', 'compile', 'execfile',
        '__import__',
        'globals', 'locals', 'vars', 'dir',
        'system', 'popen', 'spawn', 'exec', 'fork',
        'input', 'raw_input',
    }

    DANGEROUS_MODULES = {
        'os', 'subprocess', 'commands', 'popen2',
        'socket', 'ssl', 'asyncore', 'asynchat',
        'multiprocessing', 'threading', '_thread',
        'importlib', 'imp', 'pkgutil',
        'ctypes', '_ctypes', 'cffi',
        'pickle', 'cPickle', 'marshal', 'shelve',
        'shutil',
        'signal', 'posix',
        'sys', 'platform',
        'pty', 'fcntl', 'pipes', 'posixpath',
    }

    DANGEROUS_ATTRIBUTES = {
        '__class__', '__bases__', '__subclasses__', '__mro__',
        '__globals__', '__code__', '__builtins__', '__dict__',
        '__getattribute__', '__setattr__', '__delattr__',
        '__reduce__', '__reduce_ex__', '__import__',
    }

    MALICIOUS_PATTERNS = [
        r'__import__\s*\(',
        r'eval\s*\(',
        r'exec\s*\(',
        r'compile\s*\(',
        r'__class__',
        r'__bases__',
        r'__subclasses__',
        r'__globals__',
        r'__builtins__',
        r'getattr\s*\([^,]+,\s*[\'\"]__',
        r'setattr\s*\([^,]+,\s*[\'\"]__',
        r'open\s*\([\'\"]\/etc\/',
        r'open\s*\([\'\"]C:\\\\Windows',
        r'subprocess\.',
        r'os\.system',
        r'os\.popen',
        r'shutil\.rmtree',
        r'rm\s+-rf',
        r'del\s+/s',
        r'format\s+c:',
        r'mkfs',
        r'dd\s+if=',
    ]

    def __init__(self, allowed_libraries: List[str], library_manager: LibraryManager = None):
        self.allowed_libraries = set(lib.lower() for lib in allowed_libraries)
        self.library_manager = library_manager

    def validate(self, code: str) -> Tuple[bool, str]:
        pattern_error = self._check_malicious_patterns(code)
        if pattern_error:
            return False, pattern_error

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"

        ast_error = self._check_ast_nodes(tree)
        if ast_error:
            return False, ast_error

        return True, ""

    def extract_required_libraries(self, code: str) -> List[str]:
        """从代码中提取所需的库列表"""
        required = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split('.')[0].lower()
                        if module_name not in self.DANGEROUS_MODULES:
                            required.append(module_name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_name = node.module.split('.')[0].lower()
                        if module_name not in self.DANGEROUS_MODULES:
                            required.append(module_name)
        except SyntaxError:
            pass
        return list(set(required))

    def ensure_libraries(self, libraries: List[str]) -> Tuple[bool, Dict[str, str]]:
        """确保所有需要的库都已安装"""
        if not self.library_manager:
            return True, {}
        
        results = {}
        all_success = True
        
        for lib in libraries:
            if lib in self.allowed_libraries:
                success, message = self.library_manager.ensureLibrary(lib)
                results[lib] = message
                if not success:
                    all_success = False
        
        return all_success, results

    def _check_malicious_patterns(self, code: str) -> Optional[str]:
        """检查恶意代码模式"""
        for pattern in self.MALICIOUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return f"检测到可疑代码模式，禁止执行"
        return None

    def _check_ast_nodes(self, tree: ast.AST) -> Optional[str]:
        """检查 AST 节点"""
        for node in ast.walk(tree):
            # 检查导入语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0].lower()
                    if module_name in self.DANGEROUS_MODULES:
                        if module_name not in self.allowed_libraries:
                            return f"禁止导入危险模块: {alias.name}"
                    elif module_name not in self.allowed_libraries:
                        return f"不允许导入模块: {alias.name}"

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0].lower()
                    if module_name in self.DANGEROUS_MODULES:
                        if module_name not in self.allowed_libraries:
                            return f"禁止从危险模块导入: {node.module}"
                    elif module_name not in self.allowed_libraries:
                        return f"不允许从模块导入: {node.module}"

            # 检查函数调用
            if isinstance(node, ast.Call):
                func_name = self._get_func_name(node.func)
                if func_name:
                    # 检查危险函数
                    func_base = func_name.split('.')[-1]
                    if func_base in self.DANGEROUS_FUNCTIONS:
                        return f"禁止使用危险函数: {func_name}"
                    # 检查完整路径
                    if func_name in self.DANGEROUS_FUNCTIONS:
                        return f"禁止使用危险函数: {func_name}"

            # 检查属性访问
            if isinstance(node, ast.Attribute):
                if node.attr in self.DANGEROUS_ATTRIBUTES:
                    return f"禁止访问危险属性: {node.attr}"

            # 检查名称引用
            if isinstance(node, ast.Name):
                if node.id in self.DANGEROUS_ATTRIBUTES:
                    return f"禁止访问危险属性: {node.id}"

        return None

    def _get_func_name(self, node) -> Optional[str]:
        """获取函数名"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value_name = self._get_func_name(node.value)
            if value_name:
                return f"{value_name}.{node.attr}"
            return node.attr
        return None


class CodeExecutor:
    """代码执行器"""
    
    def __init__(
        self,
        timeout: int = 30,
        max_output_length: int = 5000,
        allowed_libraries: List[str] = None,
        work_dir: str = None,
        module_json_path: str = None,
        auto_install_libraries: bool = True,
    ):
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.allowed_libraries = allowed_libraries or []
        
        self.library_manager = LibraryManager(
            moduleJsonPath=module_json_path,
            autoInstall=auto_install_libraries
        )
        
        self.validator = CodeValidator(self.allowed_libraries, self.library_manager)
        
        if work_dir:
            self.work_dir = Path(work_dir)
            self.work_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.work_dir = Path(tempfile.mkdtemp(prefix="code_sandbox_"))
        
        print(f"[CodeExecutor] 工作目录: {self.work_dir}")
    
    def execute(self, code: str, session_vars: Dict[str, Any] = None) -> ExecutionResult:
        """
        执行Python代码
        """
        start_time = time.time()
        
        is_valid, error_msg = self.validator.validate(code)
        if not is_valid:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=error_msg,
                execution_time=0.0
            )
        
        required_libs = self.validator.extract_required_libraries(code)
        
        installed_libs = []
        for lib in required_libs:
            if lib in self.allowed_libraries:
                was_installed = lib in self.library_manager.config.libraries and self.library_manager.config.libraries[lib].installed
                success, message = self.library_manager.ensureLibrary(lib)
                if success and not was_installed:
                    installed_libs.append(lib)
        
        libs_ready, lib_results = self.validator.ensure_libraries(required_libs)
        
        if not libs_ready:
            failed_libs = [lib for lib, msg in lib_results.items() if "失败" in msg or "未安装" in msg]
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"库安装失败: {', '.join(failed_libs)}\n详细信息:\n" + "\n".join([f"  - {k}: {v}" for k, v in lib_results.items()]),
                execution_time=0.0,
                installed_libraries=installed_libs
            )
        
        files_before = set(self.work_dir.glob("*"))
        
        exec_script = self._prepare_exec_script(code, session_vars)
        script_path = self.work_dir / "_exec_script.py"
        
        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(exec_script)
            
            env = self._prepare_env()
            
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.work_dir),
                env=env,
            )
            
            stdout = result.stdout
            stderr = result.stderr
            
            try:
                if stdout.strip():
                    output_data = json.loads(stdout.strip())
                    actual_stdout = output_data.get("stdout", "")
                    actual_stderr = output_data.get("stderr", "")
                    success = output_data.get("success", result.returncode == 0)
                else:
                    actual_stdout = stdout
                    actual_stderr = stderr
                    success = result.returncode == 0
            except json.JSONDecodeError:
                actual_stdout = stdout
                actual_stderr = stderr
                success = result.returncode == 0
            
            if len(actual_stdout) > self.max_output_length:
                actual_stdout = actual_stdout[:self.max_output_length] + f"\n... (输出过长，已截断)"
            if len(actual_stderr) > self.max_output_length:
                actual_stderr = actual_stderr[:self.max_output_length] + f"\n... (错误输出过长，已截断)"
            
            files_after = set(self.work_dir.glob("*"))
            new_files = files_after - files_before - {script_path}
            
            generated_files = []
            generated_images = []
            
            for f in new_files:
                if f.is_file():
                    generated_files.append(str(f))
                    if f.suffix.lower() in {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}:
                        generated_images.append(str(f))
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=success,
                stdout=actual_stdout,
                stderr=actual_stderr,
                execution_time=execution_time,
                generated_files=generated_files,
                generated_images=generated_images,
                installed_libraries=installed_libs
            )
            
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"执行超时（超过 {self.timeout} 秒）",
                execution_time=self.timeout,
                installed_libraries=installed_libs
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"执行错误: {str(e)}\n{traceback.format_exc()}",
                execution_time=time.time() - start_time,
                installed_libraries=installed_libs
            )
    
    def _prepare_exec_script(self, code: str, session_vars: Dict[str, Any] = None) -> str:
        """准备执行脚本"""
        # 添加结果捕获逻辑和必要的初始化
        script = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import io
import json

# 设置matplotlib使用非交互式后端（必须在导入matplotlib之前）
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 捕获标准输出和错误
_stdout_capture = io.StringIO()
_stderr_capture = io.StringIO()

# 执行结果
_success = True
_error_msg = ""

try:
    # 重定向输出
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = _stdout_capture
    sys.stderr = _stderr_capture
    
    # 执行用户代码
'''
        # 添加用户代码（正确缩进）
        for line in code.split('\n'):
            script += f'    {line}\n'
        
        script += '''
    # 恢复输出
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    
except Exception as e:
    _success = False
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    import traceback
    _error_msg = str(e) + "\\n" + traceback.format_exc()

# 输出结果（JSON格式）
_result = {
    "stdout": _stdout_capture.getvalue(),
    "stderr": _stderr_capture.getvalue() if not _error_msg else _error_msg,
    "success": _success
}
print(json.dumps(_result, ensure_ascii=False))
'''
        return script
    
    def _prepare_env(self) -> dict:
        """准备环境变量"""
        return os.environ.copy()
    
    def cleanup(self):
        """清理工作目录"""
        try:
            if self.work_dir.exists():
                shutil.rmtree(self.work_dir)
        except Exception:
            pass
    
    def get_work_dir(self) -> Path:
        """获取工作目录"""
        return self.work_dir
