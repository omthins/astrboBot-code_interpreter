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


class CodeValidator:
    """代码验证器，检查代码安全性"""
    
    DANGEROUS_FUNCTIONS = {
        'eval', 'exec', 'compile', 'input',
        '__import__', 'globals', 'locals', 'vars',
        'os.system', 'os.popen', 'os.spawn', 'os.exec',
        'subprocess.call', 'subprocess.run', 'subprocess.Popen',
    }
    
    DANGEROUS_MODULES = {
        'os', 'subprocess', 'socket', 'pickle',
        'shutil', 'importlib', 'ctypes', 'multiprocessing',
        'threading', 'signal', 'pty', 'fcntl', 'pipes',
    }
    
    def __init__(self, allowed_libraries: List[str]):
        self.allowed_libraries = set(lib.lower() for lib in allowed_libraries)
    
    def validate(self, code: str) -> Tuple[bool, str]:
        """
        验证代码安全性
        返回: (是否安全, 错误信息)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        
        for node in ast.walk(tree):
            # 检查导入语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0].lower()
                    if module_name in self.DANGEROUS_MODULES:
                        if module_name not in self.allowed_libraries:
                            return False, f"禁止导入模块: {alias.name}"
                    elif module_name not in self.allowed_libraries:
                        return False, f"不允许导入模块: {alias.name}。允许的模块: {', '.join(self.allowed_libraries)}"
            
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0].lower()
                    if module_name in self.DANGEROUS_MODULES:
                        if module_name not in self.allowed_libraries:
                            return False, f"禁止从模块导入: {node.module}"
                    elif module_name not in self.allowed_libraries:
                        return False, f"不允许从模块导入: {node.module}。允许的模块: {', '.join(self.allowed_libraries)}"
            
            # 检查函数调用
            if isinstance(node, ast.Call):
                func_name = self._get_func_name(node.func)
                if func_name and func_name in self.DANGEROUS_FUNCTIONS:
                    return False, f"禁止使用函数: {func_name}"
        
        return True, ""
    
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
        enable_network: bool = False,
        allowed_libraries: List[str] = None,
        work_dir: str = None,
    ):
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.enable_network = enable_network
        self.allowed_libraries = allowed_libraries or []
        self.validator = CodeValidator(self.allowed_libraries)
        
        # 设置工作目录
        if work_dir:
            self.work_dir = Path(work_dir)
            self.work_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.work_dir = Path(tempfile.mkdtemp(prefix="code_sandbox_"))
        
        # 打印工作目录用于调试
        print(f"[CodeExecutor] 工作目录: {self.work_dir}")
    
    def execute(self, code: str, session_vars: Dict[str, Any] = None) -> ExecutionResult:
        """
        执行Python代码
        """
        start_time = time.time()
        
        # 验证代码
        is_valid, error_msg = self.validator.validate(code)
        if not is_valid:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=error_msg,
                execution_time=0.0
            )
        
        # 记录执行前的文件
        files_before = set(self.work_dir.glob("*"))
        
        # 准备执行脚本
        exec_script = self._prepare_exec_script(code, session_vars)
        script_path = self.work_dir / "_exec_script.py"
        
        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(exec_script)
            
            # 准备环境变量
            env = self._prepare_env()
            
            # 执行代码
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
            
            # 尝试解析JSON输出
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
            
            # 截断过长输出
            if len(actual_stdout) > self.max_output_length:
                actual_stdout = actual_stdout[:self.max_output_length] + f"\n... (输出过长，已截断)"
            if len(actual_stderr) > self.max_output_length:
                actual_stderr = actual_stderr[:self.max_output_length] + f"\n... (错误输出过长，已截断)"
            
            # 检测生成的文件
            files_after = set(self.work_dir.glob("*"))
            new_files = files_after - files_before - {script_path}
            
            generated_files = []
            generated_images = []
            
            for f in new_files:
                if f.is_file():
                    generated_files.append(str(f))
                    # 检测图片文件
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
            )
            
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"执行超时（超过 {self.timeout} 秒）",
                execution_time=self.timeout,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"执行错误: {str(e)}\n{traceback.format_exc()}",
                execution_time=time.time() - start_time,
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
        env = os.environ.copy()
        
        # 如果禁用网络，移除相关环境变量
        if not self.enable_network:
            # 这些只是象征性的限制，实际网络限制需要更复杂的沙箱
            env.pop('HTTP_PROXY', None)
            env.pop('HTTPS_PROXY', None)
            env.pop('http_proxy', None)
            env.pop('https_proxy', None)
        
        return env
    
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
