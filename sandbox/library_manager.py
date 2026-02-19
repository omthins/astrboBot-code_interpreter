"""
库管理器模块
负责检查、安装和记录Python库依赖
"""

import json
import subprocess
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field, asdict


@dataclass
class LibraryInfo:
    """库信息"""
    installed: bool = False
    version: Optional[str] = None
    installTime: Optional[str] = None
    description: str = ""


@dataclass
class ModuleConfig:
    """模块配置"""
    description: str = ""
    version: str = "1.0.0"
    lastUpdated: str = ""
    libraries: Dict[str, LibraryInfo] = field(default_factory=dict)
    standardLibraries: List[str] = field(default_factory=list)


class LibraryManager:
    """库管理器，负责自动化库管理流程"""
    
    STANDARD_LIBRARIES = {
        "json", "math", "statistics", "decimal", "fractions", "random", "secrets",
        "datetime", "time", "calendar", "re", "csv", "io", "pathlib", "hashlib",
        "base64", "sqlite3", "urllib.parse", "collections", "itertools", "functools",
        "typing", "xml.etree.ElementTree"
    }
    
    PACKAGE_NAME_MAP = {
        "beautifulsoup4": "bs4",
        "pillow": "PIL",
        "pyyaml": "yaml",
        "python-dateutil": "dateutil",
        "opencv-python": "cv2",
        "scikit-learn": "sklearn",
        "pycryptodome": "Crypto",
    }
    
    IMPORT_TO_PACKAGE_MAP = {v: k for k, v in PACKAGE_NAME_MAP.items()}
    
    PIP_MIRRORS = [
        ("清华", "https://pypi.tuna.tsinghua.edu.cn/simple"),
        ("阿里云", "https://mirrors.aliyun.com/pypi/simple"),
        ("腾讯", "https://mirrors.cloud.tencent.com/pypi/simple"),
        ("华为", "https://mirrors.huawei.com/pypi/simple"),
        ("豆瓣", "https://pypi.douban.com/simple/"),
        ("中科大", "https://pypi.mirrors.ustc.edu.cn/simple/"),
    ]
    
    def __init__(self, moduleJsonPath: str = None, autoInstall: bool = True, pipMirror: str = None):
        self.moduleJsonPath = Path(moduleJsonPath) if moduleJsonPath else None
        self.autoInstall = autoInstall
        self.pipMirror = pipMirror or self.PIP_MIRRORS[0][1]
        self.config: ModuleConfig = ModuleConfig()
        self._installedCache: Dict[str, bool] = {}
        
        if self.moduleJsonPath and self.moduleJsonPath.exists():
            self._loadConfig()
        else:
            self._initializeDefaultConfig()
    
    def _initializeDefaultConfig(self):
        """初始化默认配置"""
        self.config = ModuleConfig(
            description="代码解释器插件依赖库管理文件",
            version="1.0.0",
            lastUpdated=datetime.now().strftime("%Y-%m-%d"),
            libraries={},
            standardLibraries=list(self.STANDARD_LIBRARIES)
        )
    
    def _loadConfig(self):
        """从 module.json 加载配置"""
        try:
            with open(self.moduleJsonPath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            libraries = {}
            for name, info in data.get("libraries", {}).items():
                libraries[name] = LibraryInfo(
                    installed=info.get("installed", False),
                    version=info.get("version"),
                    installTime=info.get("installTime"),
                    description=info.get("description", "")
                )
            
            self.config = ModuleConfig(
                description=data.get("description", ""),
                version=data.get("version", "1.0.0"),
                lastUpdated=data.get("lastUpdated", ""),
                libraries=libraries,
                standardLibraries=data.get("standardLibraries", list(self.STANDARD_LIBRARIES))
            )
        except Exception as e:
            print(f"[LibraryManager] 加载配置失败: {e}")
            self._initializeDefaultConfig()
    
    def _saveConfig(self):
        """保存配置到 module.json"""
        if not self.moduleJsonPath:
            return
        
        try:
            data = {
                "description": self.config.description,
                "version": self.config.version,
                "lastUpdated": datetime.now().strftime("%Y-%m-%d"),
                "libraries": {},
                "standardLibraries": self.config.standardLibraries
            }
            
            for name, info in self.config.libraries.items():
                data["libraries"][name] = {
                    "installed": info.installed,
                    "version": info.version,
                    "installTime": info.installTime,
                    "description": info.description
                }
            
            with open(self.moduleJsonPath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"[LibraryManager] 保存配置失败: {e}")
    
    def _getImportName(self, packageName: str) -> str:
        """获取包的导入名称"""
        return self.PACKAGE_NAME_MAP.get(packageName, packageName)
    
    def _getPackageName(self, importName: str) -> str:
        """获取导入名对应的包名"""
        return self.IMPORT_TO_PACKAGE_MAP.get(importName, importName)
    
    def _checkLibraryInstalled(self, libraryName: str) -> Tuple[bool, Optional[str]]:
        """检查库是否已安装，返回 (是否安装, 版本号)"""
        importName = self._getImportName(libraryName)
        
        if importName in self._installedCache:
            return self._installedCache[importName], None
        
        try:
            spec = importlib.util.find_spec(importName)
            if spec is not None:
                try:
                    module = importlib.import_module(importName)
                    version = getattr(module, '__version__', None)
                    self._installedCache[importName] = True
                    return True, version
                except ImportError:
                    pass
            
            self._installedCache[importName] = False
            return False, None
            
        except (ImportError, ModuleNotFoundError, ValueError):
            self._installedCache[importName] = False
            return False, None
    
    def _installLibrary(self, packageName: str) -> Tuple[bool, str]:
        """安装库，返回 (是否成功, 消息)"""
        try:
            print(f"[LibraryManager] 正在安装库: {packageName}")
            print(f"[LibraryManager] 使用镜像源: {self.pipMirror}")
            
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", packageName, "-i", self.pipMirror, "--trusted-host", self._extractHost(self.pipMirror)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                self._installedCache.clear()
                return True, f"成功安装 {packageName}"
            else:
                error_msg = result.stderr or result.stdout
                return False, f"安装失败: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, f"安装超时（超过300秒）"
        except Exception as e:
            return False, f"安装异常: {str(e)}"
    
    def _extractHost(self, url: str) -> str:
        """从URL中提取主机名"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ""
    
    def setPipMirror(self, mirrorUrl: str):
        """设置pip镜像源"""
        self.pipMirror = mirrorUrl
        print(f"[LibraryManager] 已切换镜像源: {mirrorUrl}")
    
    def getAvailableMirrors(self) -> List[Tuple[str, str]]:
        """获取可用的镜像源列表"""
        return self.PIP_MIRRORS.copy()
    
    def ensureLibrary(self, libraryName: str, description: str = "") -> Tuple[bool, str]:
        """
        确保库已安装
        这是核心方法，实现了完整的自动化库管理流程：
        1. 检查 module.json 中是否已记录
        2. 检查实际是否已安装
        3. 若未安装则执行安装
        4. 更新 module.json 记录
        
        返回: (是否可用, 消息)
        """
        if libraryName in self.STANDARD_LIBRARIES:
            return True, "标准库，无需安装"
        
        packageName = self._getPackageName(libraryName)
        importName = self._getImportName(packageName)
        
        if packageName in self.config.libraries:
            libInfo = self.config.libraries[packageName]
            if libInfo.installed:
                actualInstalled, version = self._checkLibraryInstalled(packageName)
                if actualInstalled:
                    return True, f"库已安装: {packageName}"
                else:
                    libInfo.installed = False
                    libInfo.version = None
                    libInfo.installTime = None
        
        actualInstalled, version = self._checkLibraryInstalled(packageName)
        if actualInstalled:
            self.config.libraries[packageName] = LibraryInfo(
                installed=True,
                version=version,
                installTime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                description=description or f"自动检测已安装"
            )
            self._saveConfig()
            return True, f"库已安装: {packageName} (版本: {version or '未知'})"
        
        if not self.autoInstall:
            return False, f"库未安装且自动安装已禁用: {packageName}"
        
        success, message = self._installLibrary(packageName)
        if success:
            installed, version = self._checkLibraryInstalled(packageName)
            self.config.libraries[packageName] = LibraryInfo(
                installed=installed,
                version=version,
                installTime=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                description=description or "自动安装"
            )
            self._saveConfig()
            return True, f"成功安装库: {packageName}"
        else:
            self.config.libraries[packageName] = LibraryInfo(
                installed=False,
                description=description or f"安装失败: {message}"
            )
            self._saveConfig()
            return False, message
    
    def ensureLibraries(self, libraries: List[str]) -> Tuple[bool, Dict[str, str]]:
        """
        批量确保多个库已安装
        返回: (是否全部成功, {库名: 消息})
        """
        results = {}
        allSuccess = True
        
        for lib in libraries:
            success, message = self.ensureLibrary(lib)
            results[lib] = message
            if not success:
                allSuccess = False
        
        return allSuccess, results
    
    def getInstalledLibraries(self) -> List[str]:
        """获取所有已安装的库列表"""
        installed = list(self.STANDARD_LIBRARIES)
        
        for name, info in self.config.libraries.items():
            if info.installed:
                installed.append(name)
        
        return installed
    
    def getLibraryStatus(self, libraryName: str) -> Dict:
        """获取库的详细状态"""
        if libraryName in self.STANDARD_LIBRARIES:
            return {
                "name": libraryName,
                "type": "standard",
                "installed": True,
                "version": None,
                "description": "Python标准库"
            }
        
        packageName = self._getPackageName(libraryName)
        
        if packageName in self.config.libraries:
            info = self.config.libraries[packageName]
            return {
                "name": packageName,
                "type": "third-party",
                "installed": info.installed,
                "version": info.version,
                "installTime": info.installTime,
                "description": info.description
            }
        
        installed, version = self._checkLibraryInstalled(packageName)
        return {
            "name": packageName,
            "type": "third-party",
            "installed": installed,
            "version": version,
            "description": "未记录"
        }
    
    def refreshLibraryStatus(self) -> Dict[str, Dict]:
        """刷新所有库的安装状态"""
        updated = {}
        
        for name, info in self.config.libraries.items():
            installed, version = self._checkLibraryInstalled(name)
            if installed != info.installed or version != info.version:
                info.installed = installed
                info.version = version
                if installed and not info.installTime:
                    info.installTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                updated[name] = {
                    "installed": installed,
                    "version": version
                }
        
        if updated:
            self._saveConfig()
        
        return updated
    
    def addLibraryRecord(self, libraryName: str, description: str = "") -> bool:
        """添加库记录（不安装）"""
        if libraryName in self.STANDARD_LIBRARIES:
            return True
        
        packageName = self._getPackageName(libraryName)
        installed, version = self._checkLibraryInstalled(packageName)
        
        self.config.libraries[packageName] = LibraryInfo(
            installed=installed,
            version=version,
            installTime=datetime.now().strftime("%Y-%m-%d %H:%M:%S") if installed else None,
            description=description
        )
        self._saveConfig()
        return True
    
    def removeLibraryRecord(self, libraryName: str) -> bool:
        """移除库记录"""
        packageName = self._getPackageName(libraryName)
        if packageName in self.config.libraries:
            del self.config.libraries[packageName]
            self._saveConfig()
            return True
        return False
