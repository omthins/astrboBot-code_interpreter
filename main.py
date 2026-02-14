"""
AstrBot 代码解释器插件
支持LLM生成并执行Python代码，并提供结果可视化
"""

import json
import re
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import asdict

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api import AstrBotConfig
from astrbot.api.message_components import Image, Plain

from .sandbox.executor import CodeExecutor, ExecutionResult


# 代码解释器工具的系统提示
CODE_INTERPRETER_SYSTEM_PROMPT = """你是一个专业的代码解释器助手。当用户的问题需要计算、数据处理、文件操作、绘图等功能时，你应该生成Python代码来解决问题。

## 重要：工作目录
**所有生成的文件默认保存在 D:\\BotCode 目录下。** 如果该目录不存在会自动创建。
- 保存图片时使用简单文件名，如 'plot.png', 'chart.png'
- 保存文件时使用相对路径，文件会自动保存到工作目录

## 代码生成规则：
1. 代码应该是完整可执行的Python代码
2. 使用 print() 输出结果
3. **重要**: 如果需要绑图，必须使用 plt.savefig('filename.png') 保存图片，**绝对不要使用 plt.show()**
4. 图片文件名使用简单的英文名，如 'plot.png', 'chart.png' 等
5. 如果需要处理数据，优先使用 pandas
6. 代码不要包含 input() 函数
7. 所有输出通过 print() 输出

## 可用库：
- numpy: 数值计算
- pandas: 数据处理和分析
- matplotlib: 绑图（必须用 savefig 保存图片）
- pillow: 图像处理
- seaborn: 统计图表
- qrcode: 二维码生成
- wordcloud: 词云生成
- sympy: 符号数学
- openpyxl: Excel 读写
- beautifulsoup4: HTML 解析
- json: JSON处理
- math, statistics, decimal, fractions: 数学计算
- random, secrets: 随机数
- datetime, time, calendar: 时间日期
- re: 正则表达式
- csv, io, pathlib: 文件操作
- hashlib, base64: 编码加密
- sqlite3: 数据库
- urllib.parse: URL 解析
- collections, itertools, functools: 工具库

## 响应格式：
当需要执行代码时，请使用以下格式包裹代码：
```python
# 你的代码
```

如果只是普通对话，直接回答即可。

## 示例代码：
```python
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 10, 100)
plt.plot(x, np.sin(x))
plt.savefig('sin.png')  # 文件会保存到 D:\\BotCode\\sin.png
print('图像已保存')
```"""


# 代码生成工具定义（用于 function calling）
CODE_TOOL_DESCRIPTION = """当用户的问题需要以下能力时，使用此工具生成并执行Python代码：
- 数学计算或复杂运算
- 数据处理、分析或可视化
- 生成图表或图片
- 文件操作
- 需要编程解决的问题

工具会执行代码并返回结果。"""


@register(
    "code_interpreter",
    "Your Name",
    "一个代码解释器插件，支持LLM生成并执行Python代码",
    "1.0.8",
    "https://github.com/your-repo/astrbot_plugin_code_interpreter"
)
class CodeInterpreterPlugin(Star):
    """代码解释器插件主类"""
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 初始化配置
        self.timeout = config.get("timeout", 30)
        self.max_output_length = config.get("max_output_length", 5000)
        self.enable_network = config.get("enable_network", False)
        self.allowed_libraries = config.get("allowed_libraries", [
            "numpy", "pandas", "matplotlib", "pillow", "requests",
            "json", "math", "random", "datetime", "re", "collections", "itertools",
            "csv", "hashlib", "base64", "secrets", "statistics", "decimal", "fractions",
            "functools", "pathlib", "time", "calendar", "io", "sqlite3", "typing",
            "xml.etree.ElementTree", "urllib.parse", "qrcode", "seaborn", "openpyxl",
            "beautifulsoup4", "wordcloud", "sympy"
        ])
        self.auto_retry = config.get("auto_retry", True)
        self.max_retry_count = config.get("max_retry_count", 2)
        self.show_execution_time = config.get("show_execution_time", True)
        
        # 工作目录固定为 D:\BotCode，如果不存在则自动创建
        self.work_dir = "D:\\BotCode"
        Path(self.work_dir).mkdir(parents=True, exist_ok=True)
        
        # 可视化配置
        viz_config = config.get("visualization", {})
        self.enable_table_markdown = viz_config.get("enable_table_markdown", True)
        self.enable_image_display = viz_config.get("enable_image_display", True)
        self.enable_json_format = viz_config.get("enable_json_format", True)
        self.enable_code_render = viz_config.get("enable_code_render", True)
        
        # 会话执行器缓存
        self._executors: Dict[str, CodeExecutor] = {}
        
        # 获取模板路径
        self.template_path = Path(__file__).parent / "templates" / "result.html"
        
        logger.info(f"代码解释器插件已加载，超时时间: {self.timeout}s，工作目录: {self.work_dir}")

    def _get_executor(self, session_id: str) -> CodeExecutor:
        """获取或创建会话执行器"""
        # 清理 session_id 中的无效字符（Windows 不允许 : 在文件名中）
        safe_session_id = session_id.replace(":", "_").replace("/", "_").replace("\\", "_")
        
        if safe_session_id not in self._executors:
            # 确保工作目录存在
            base_work_dir = Path(self.work_dir)
            base_work_dir.mkdir(parents=True, exist_ok=True)
            
            # 为每个会话创建子目录
            work_dir = base_work_dir / safe_session_id
            work_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"[CodeInterpreter] 创建执行器，工作目录: {work_dir}")
            
            self._executors[safe_session_id] = CodeExecutor(
                timeout=self.timeout,
                max_output_length=self.max_output_length,
                enable_network=self.enable_network,
                allowed_libraries=self.allowed_libraries,
                work_dir=str(work_dir),
            )
        return self._executors[safe_session_id]

    def _extract_code(self, text: str) -> Optional[str]:
        """从文本中提取Python代码块"""
        # 匹配 ```python ... ``` 或 ``` ... ```
        # 更健壮的正则，处理各种换行和空格情况
        patterns = [
            r'```python\s*([\s\S]*?)```',
            r'```Python\s*([\s\S]*?)```',
            r'```\s*([\s\S]*?)```',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                code = match.strip()
                # 确保提取到的是有效代码
                if code and len(code) > 0:
                    logger.debug(f"提取到代码块: {code[:100]}...")
                    return code
        return None

    def _format_output(self, result: ExecutionResult, code: str) -> Dict[str, Any]:
        """格式化输出结果"""
        output_parts = []
        
        # 基本输出
        output = result.stdout if result.success else result.stderr
        
        # 尝试检测和格式化不同类型的输出
        formatted_data = {
            "raw_output": output,
            "is_json": False,
            "is_table": False,
            "json_data": None,
            "table_html": None,
        }
        
        # 尝试解析为JSON
        if self.enable_json_format and output.strip():
            try:
                parsed = json.loads(output.strip())
                formatted_data["is_json"] = True
                formatted_data["json_data"] = json.dumps(parsed, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        
        # 检测Markdown表格
        if self.enable_table_markdown:
            table_html = self._parse_markdown_table(output)
            if table_html:
                formatted_data["is_table"] = True
                formatted_data["table_html"] = table_html
        
        return formatted_data

    def _parse_markdown_table(self, text: str) -> Optional[str]:
        """解析Markdown表格并转换为HTML"""
        lines = text.strip().split('\n')
        table_lines = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('|') and line.endswith('|'):
                table_lines.append(line)
        
        if len(table_lines) < 2:
            return None
        
        # 解析表头
        headers = [cell.strip() for cell in table_lines[0].split('|')[1:-1]]
        
        # 跳过分隔行
        data_lines = table_lines[2:] if len(table_lines) > 2 else []
        
        # 生成HTML
        html = '<table class="markdown-table">\n<thead>\n<tr>\n'
        for header in headers:
            html += f'<th>{header}</th>\n'
        html += '</tr>\n</thead>\n<tbody>\n'
        
        for line in data_lines:
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            html += '<tr>\n'
            for cell in cells:
                html += f'<td>{cell}</td>\n'
            html += '</tr>\n'
        
        html += '</tbody>\n</table>'
        return html

    async def _render_result_image(
        self,
        event: AstrMessageEvent,
        code: str,
        result: ExecutionResult,
        formatted_data: Dict[str, Any]
    ) -> Optional[str]:
        """渲染结果为图片"""
        try:
            # 准备模板数据
            template_data = {
                "code": code,
                "output": formatted_data.get("raw_output", ""),
                "status": "success" if result.success else "error",
                "status_icon": "✅" if result.success else "❌",
                "status_text": "成功" if result.success else "失败",
                "execution_time": f"{result.execution_time:.2f}" if self.show_execution_time else None,
                "show_code": True,
                "show_output": True,
                "show_table": formatted_data.get("is_table", False),
                "table_html": formatted_data.get("table_html"),
                "show_json": formatted_data.get("is_json", False),
                "json_output": formatted_data.get("json_data"),
                "images": [],  # 图片单独处理
            }
            
            # 读取模板
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
            
            # 使用 Jinja2 渲染（AstrBot内置支持）
            image_url = await self.html_render(template_content, template_data)
            return image_url
            
        except Exception as e:
            logger.error(f"渲染结果图片失败: {e}")
            return None

    @filter.llm_tool(name="execute_python_code")
    async def execute_python_code(self, event: AstrMessageEvent, code: str) -> MessageEventResult:
        """执行Python代码并返回结果。
        
        Args:
            code(string): 要执行的Python代码
        """
        session_id = event.unified_msg_origin
        executor = self._get_executor(session_id)
        
        logger.info(f"执行代码: {code[:100]}...")
        
        # 执行代码
        result = executor.execute(code)
        
        # 格式化输出
        formatted_data = self._format_output(result, code)
        
        # 构建响应
        response_parts = []
        
        # 如果有生成的图片，优先发送图片
        if self.enable_image_display and result.generated_images:
            for img_path in result.generated_images:
                response_parts.append(f"[图片: {Path(img_path).name}]")
        
        # 构建文本响应
        if result.success:
            output_text = formatted_data.get("json_data") or formatted_data.get("raw_output", "执行成功（无输出）")
            
            if self.show_execution_time:
                response_text = f"✅ 执行成功 ({result.execution_time:.2f}s)\n\n{output_text}"
            else:
                response_text = f"✅ 执行成功\n\n{output_text}"
        else:
            response_text = f"❌ 执行失败\n\n{result.stderr}"
        
        response_parts.insert(0, response_text)
        
        yield event.plain_result("\n".join(response_parts))

    @filter.command("code")
    async def execute_code_command(self, event: AstrMessageEvent, code: str):
        """直接执行Python代码。
        
        用法: /code <python代码>
        示例: /code print(sum(range(1, 101)))
        """
        session_id = event.unified_msg_origin
        executor = self._get_executor(session_id)
        
        logger.info(f"直接执行代码: {code[:100]}...")
        
        # 执行代码
        result = executor.execute(code)
        
        # 格式化输出
        formatted_data = self._format_output(result, code)
        
        # 构建响应消息链
        message_chain = []
        
        # 如果启用代码渲染，生成图片
        if self.enable_code_render:
            image_url = await self._render_result_image(event, code, result, formatted_data)
            if image_url:
                message_chain.append(Image.fromURL(image_url))
        
        # 如果有生成的图片，添加到消息链
        if self.enable_image_display and result.generated_images:
            for img_path in result.generated_images:
                try:
                    # 使用 file:/// 协议发送本地图片
                    message_chain.append(Image(file=f"file:///{img_path}"))
                except Exception as e:
                    logger.error(f"发送图片失败: {e}")
                    message_chain.append(Plain(f"[图片发送失败: {Path(img_path).name}]"))
        
        # 如果没有渲染图片或渲染失败，添加文本结果
        if not self.enable_code_render or not message_chain:
            if result.success:
                output_text = formatted_data.get("json_data") or formatted_data.get("raw_output", "执行成功（无输出）")
                if self.show_execution_time:
                    message_chain.append(Plain(f"✅ 执行成功 ({result.execution_time:.2f}s)\n\n{output_text}"))
                else:
                    message_chain.append(Plain(f"✅ 执行成功\n\n{output_text}"))
            else:
                message_chain.append(Plain(f"❌ 执行失败\n\n{result.stderr}"))
        
        if message_chain:
            yield event.chain_result(message_chain)

    @filter.command("code_help")
    async def code_help(self, event: AstrMessageEvent):
        """显示代码解释器帮助信息。"""
        help_text = """💻 代码解释器帮助

功能：
• 直接执行Python代码
• 通过LLM对话自动生成并执行代码
• 支持数据可视化（图片、表格、JSON）

指令：
• /code <代码> - 直接执行Python代码
• /code_help - 显示此帮助信息

可用库：
• numpy - 数值计算
• pandas - 数据处理
• matplotlib - 绑图
• pillow - 图像处理
• json, math, random, datetime, re 等

示例：
/code print(sum(range(1, 101)))
/code import matplotlib.pyplot as plt; plt.plot([1,2,3]); plt.savefig('test.png'); print('图表已保存')

提示：
直接向机器人发送需要计算或处理的问题，LLM会自动判断是否需要生成代码。"""
        
        yield event.plain_result(help_text)

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        """在LLM请求前注入系统提示"""
        try:
            logger.info("[CodeInterpreter] on_llm_request 钩子被触发")
            
            # 检查 req 对象是否有 system_prompt 属性
            if hasattr(req, 'system_prompt'):
                current_prompt = req.system_prompt or ""
                if CODE_INTERPRETER_SYSTEM_PROMPT not in current_prompt:
                    req.system_prompt = current_prompt + "\n\n" + CODE_INTERPRETER_SYSTEM_PROMPT
                    logger.debug("[CodeInterpreter] 系统提示已注入")
            else:
                logger.warning("[CodeInterpreter] req 对象没有 system_prompt 属性")
                
        except Exception as e:
            logger.error(f"[CodeInterpreter] on_llm_request 错误: {e}")
            import traceback
            logger.error(traceback.format_exc())

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp):
        """处理LLM响应，检测并执行代码"""
        try:
            logger.info("[CodeInterpreter] on_llm_response 钩子被触发")
            
            # 安全获取响应文本
            response_text = ""
            if hasattr(resp, 'completion_text'):
                response_text = resp.completion_text or ""
            elif hasattr(resp, 'text'):
                response_text = resp.text or ""
            else:
                logger.warning(f"[CodeInterpreter] resp 对象类型: {type(resp)}, 属性: {dir(resp)}")
                return
            
            logger.info(f"[CodeInterpreter] LLM响应长度: {len(response_text)}")
            logger.debug(f"[CodeInterpreter] LLM响应内容: {response_text[:500]}...")
            
            # 检测响应中是否包含代码块
            code = self._extract_code(response_text)
            
            if not code:
                # 没有代码，正常返回
                logger.debug("[CodeInterpreter] 未检测到代码块，正常返回")
                return
            
            logger.info(f"[CodeInterpreter] 检测到代码块，准备执行:\n{code}")
            
            session_id = event.unified_msg_origin
            executor = self._get_executor(session_id)
            
            # 执行代码（支持重试）
            result, final_code, retry_count = await self._execute_with_retry(
                event, executor, code
            )
            
            logger.info(f"[CodeInterpreter] 执行完成: success={result.success}, time={result.execution_time:.2f}s, retries={retry_count}")
            if result.generated_images:
                logger.info(f"[CodeInterpreter] 生成图片: {result.generated_images}")
            if result.generated_files:
                logger.info(f"[CodeInterpreter] 生成文件: {result.generated_files}")
            
            # 格式化输出
            formatted_data = self._format_output(result, final_code)
            
            # 构建响应消息链
            message_chain = []
            
            # 添加LLM的原始响应（去除代码块部分）
            clean_response = re.sub(r'```python\s*[\s\S]*?```', '', response_text, flags=re.IGNORECASE)
            clean_response = re.sub(r'```\s*[\s\S]*?```', '', clean_response, flags=re.IGNORECASE)
            clean_response = clean_response.strip()
            
            if clean_response:
                message_chain.append(Plain(clean_response + "\n"))
            
            # 如果有生成的图片，优先发送图片
            if self.enable_image_display and result.generated_images:
                for img_path in result.generated_images:
                    try:
                        logger.info(f"[CodeInterpreter] 发送图片: {img_path}")
                        message_chain.append(Image(file=f"file:///{img_path}"))
                    except Exception as img_err:
                        logger.error(f"[CodeInterpreter] 发送图片失败: {img_err}")
                        message_chain.append(Plain(f"[图片: {Path(img_path).name}]"))
            
            # 添加文本结果
            if result.success:
                output_text = formatted_data.get("json_data") or formatted_data.get("raw_output", "")
                if output_text:
                    if self.show_execution_time:
                        message_chain.append(Plain(f"\n✅ 执行成功 ({result.execution_time:.2f}s)\n\n{output_text}"))
                    else:
                        message_chain.append(Plain(f"\n✅ 执行成功\n\n{output_text}"))
                # 如果有重试，显示重试次数
                if retry_count > 0:
                    message_chain.append(Plain(f"\n🔄 自动修正 {retry_count} 次后成功"))
            else:
                # 执行失败，显示友好提示
                error_msg = result.stderr
                if retry_count >= self.max_retry_count:
                    error_msg = f"已尝试修正 {retry_count} 次，仍然失败。\n\n错误信息:\n{result.stderr}"
                message_chain.append(Plain(f"\n❌ 代码执行失败\n\n{error_msg}"))
            
            # 发送结果
            if message_chain:
                await event.send(event.chain_result(message_chain))
                event.stop_event()
                logger.info("[CodeInterpreter] 结果已发送，事件已停止")
                
        except Exception as e:
            logger.error(f"[CodeInterpreter] 处理代码执行时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 发生错误时不阻止正常响应
            return

    async def _execute_with_retry(
        self,
        event: AstrMessageEvent,
        executor: CodeExecutor,
        initial_code: str
    ) -> tuple:
        """
        执行代码并支持自动重试
        返回: (最终执行结果, 最终代码, 重试次数)
        """
        code = initial_code
        retry_count = 0
        last_error = ""
        
        while True:
            # 执行代码
            result = executor.execute(code)
            
            # 如果成功，直接返回
            if result.success:
                return result, code, retry_count
            
            # 如果禁用自动重试或已达到最大重试次数，返回失败结果
            if not self.auto_retry or retry_count >= self.max_retry_count:
                return result, code, retry_count
            
            # 记录错误
            last_error = result.stderr
            logger.info(f"[CodeInterpreter] 代码执行失败，尝试让LLM修正 (第 {retry_count + 1} 次重试)")
            
            # 尝试让 LLM 修正代码
            retry_count += 1
            fixed_code = await self._get_fixed_code(event, code, last_error, retry_count)
            
            if fixed_code and fixed_code != code:
                code = fixed_code
                logger.info(f"[CodeInterpreter] 获取到修正后的代码，重新执行")
            else:
                # 无法获取修正代码，返回失败结果
                logger.warning("[CodeInterpreter] 未能获取修正后的代码")
                return result, code, retry_count

    async def _get_fixed_code(
        self,
        event: AstrMessageEvent,
        original_code: str,
        error_message: str,
        retry_count: int
    ) -> Optional[str]:
        """
        让 LLM 修正错误的代码
        """
        try:
            # 构建修正请求
            fix_prompt = f"""你的代码执行失败了，请根据错误信息修正代码。

原始代码:
```python
{original_code}
```

错误信息:
{error_message}

请直接输出修正后的完整代码，用 ```python ``` 包裹。不要解释，只输出修正后的代码。"""

            # 尝试通过 context 调用 LLM
            if hasattr(self, 'context') and hasattr(self.context, 'call_llm'):
                response = await self.context.call_llm(fix_prompt)
                if response:
                    fixed_code = self._extract_code(response)
                    if fixed_code:
                        return fixed_code
            
            # 尝试通过 llm_tool 方式
            if hasattr(event, 'request_llm'):
                response = await event.request_llm(fix_prompt)
                if response:
                    fixed_code = self._extract_code(str(response))
                    if fixed_code:
                        return fixed_code
            
            # 尝试通过 _llm_manager 调用
            if hasattr(self.context, '_llm_manager') and self.context._llm_manager:
                llm_manager = self.context._llm_manager
                if hasattr(llm_manager, 'call'):
                    response = await llm_manager.call(fix_prompt)
                    if response:
                        fixed_code = self._extract_code(str(response))
                        if fixed_code:
                            return fixed_code
            
            # 如果以上方法都不可用，尝试简单的代码自动修复
            return self._auto_fix_code(original_code, error_message)
            
        except Exception as e:
            logger.error(f"[CodeInterpreter] 获取修正代码失败: {e}")
            return None

    def _auto_fix_code(self, code: str, error_message: str) -> Optional[str]:
        """
        尝试自动修复常见的代码错误
        """
        # 修复语法错误：invalid decimal literal
        if "invalid decimal literal" in error_message:
            # 尝试修复数字和字符串连写的问题，如 print("结果"5) -> print("结果", 5)
            import re as regex
            # 查找类似 "text"数字 的模式
            code = regex.sub(r'"([^"]*)"(\d+)', r'"\1", \2', code)
            code = regex.sub(r"'([^']*)'(\d+)", r"'\1', \2", code)
            code = regex.sub(r'(\d+)"([^"]*)"', r'\1, "\2"', code)
            code = regex.sub(r"(\d+)'([^']*)'", r"\1, '\2'", code)
            return code
        
        # 修复未闭合的括号
        if "unterminated string literal" in error_message or "EOL while scanning string literal" in error_message:
            # 统计引号数量
            single_quotes = code.count("'") - code.count("\\'")
            double_quotes = code.count('"') - code.count('\\"')
            if single_quotes % 2 != 0:
                code += "'"
            if double_quotes % 2 != 0:
                code += '"'
            return code
        
        # 修复缩进错误
        if "unindent does not match" in error_message or "expected an indented block" in error_message:
            lines = code.split('\n')
            fixed_lines = []
            for line in lines:
                if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                    # 可能需要缩进的行
                    if any(kw in line for kw in ['print', 'return', 'yield', 'break', 'continue', 'pass']):
                        line = '    ' + line
                fixed_lines.append(line)
            return '\n'.join(fixed_lines)
        
        return None

    async def terminate(self):
        """插件卸载时清理资源"""
        # 清理所有执行器
        for executor in self._executors.values():
            executor.cleanup()
        self._executors.clear()
        logger.info("代码解释器插件已卸载")
