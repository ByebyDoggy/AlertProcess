#!/usr/bin/env python3
"""
开发者环境初始化脚本

用法:
    python scripts/init_developer_env.py alice
    python scripts/init_developer_env.py bob
"""

import sys
import os
import shutil
from pathlib import Path

def init_developer_env(developer_name: str):
    """初始化开发者环境"""

    project_root = Path(__file__).parent.parent

    print(f"🚀 初始化开发者环境: {developer_name}")
    print(f"📁 项目根目录: {project_root}")

    # 1. 创建个人配置文件
    env_file = project_root / f".env.{developer_name}"
    env_example = project_root / ".env.example"

    if env_file.exists():
        print(f"⚠️  配置文件已存在: {env_file}")
        overwrite = input("是否覆盖? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("❌ 跳过配置文件创建")
        else:
            shutil.copy(env_example, env_file)
            print(f"✅ 已创建配置文件: {env_file}")
    else:
        shutil.copy(env_example, env_file)
        print(f"✅ 已创建配置文件: {env_file}")

    # 2. 更新配置文件中的 DEVELOPER_NAME
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 取消注释并设置 DEVELOPER_NAME
        content = content.replace(
            "# DEVELOPER_NAME=alice",
            f"DEVELOPER_NAME={developer_name}"
        )

        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"✅ 已设置 DEVELOPER_NAME={developer_name}")

    # 3. 创建个人数据库（如果不存在）
    db_file = project_root / f"alerts_{developer_name}.db"
    base_db = project_root / "alerts.db"

    if db_file.exists():
        print(f"⚠️  数据库已存在: {db_file}")
    elif base_db.exists():
        # 复制基础数据库
        shutil.copy(base_db, db_file)
        print(f"✅ 已复制数据库: {db_file}")
    else:
        print(f"ℹ️  基础数据库不存在，将在首次启动时创建: {db_file}")

    # 4. 创建环境变量设置脚本
    shell_script = project_root / f"activate_{developer_name}.sh"
    with open(shell_script, 'w', encoding='utf-8') as f:
        f.write(f"""#!/bin/bash
# 激活 {developer_name} 的开发环境

export DEVELOPER_NAME={developer_name}

echo "✅ 已激活开发者环境: {developer_name}"
echo "📊 数据库: alerts_{developer_name}.db"
echo ""
echo "启动服务:"
echo "  python main.py"
echo ""
echo "或者使用 uvicorn:"
echo "  uvicorn main:app --reload --port 8000"
""")

    # Windows 批处理脚本
    bat_script = project_root / f"activate_{developer_name}.bat"
    with open(bat_script, 'w', encoding='utf-8') as f:
        f.write(f"""@echo off
REM 激活 {developer_name} 的开发环境

set DEVELOPER_NAME={developer_name}

echo ✅ 已激活开发者环境: {developer_name}
echo 📊 数据库: alerts_{developer_name}.db
echo.
echo 启动服务:
echo   python main.py
echo.
echo 或者使用 uvicorn:
echo   uvicorn main:app --reload --port 8000
""")

    print(f"✅ 已创建激活脚本:")
    print(f"   - Linux/Mac: source activate_{developer_name}.sh")
    print(f"   - Windows: activate_{developer_name}.bat")

    # 5. 显示使用说明
    print("\n" + "="*60)
    print("🎉 开发者环境初始化完成！")
    print("="*60)
    print("\n📝 使用说明:\n")
    print("1. 激活环境:")
    print(f"   Linux/Mac: source activate_{developer_name}.sh")
    print(f"   Windows:   activate_{developer_name}.bat")
    print("\n2. 启动服务:")
    print("   python main.py")
    print("\n3. 验证配置:")
    print("   - 检查日志中的数据库路径")
    print(f"   - 应该看到: sqlite:///./alerts_{developer_name}.db")
    print("\n4. 编辑个人配置:")
    print(f"   vim .env.{developer_name}")
    print("\n" + "="*60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/init_developer_env.py <developer_name>")
        print("\n示例:")
        print("  python scripts/init_developer_env.py alice")
        print("  python scripts/init_developer_env.py bob")
        sys.exit(1)

    developer_name = sys.argv[1]

    # 验证开发者名称
    if not developer_name.isalnum():
        print(f"❌ 错误: 开发者名称只能包含字母和数字: {developer_name}")
        sys.exit(1)

    init_developer_env(developer_name)
