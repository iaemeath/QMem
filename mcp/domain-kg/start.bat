@echo off
REM DomainKG (business concept graph) Python MCP server launcher
REM Usage: start.bat [python_path]
REM Requires: Python 3.10+ with sqlite-vec, onnxruntime, tokenizers, numpy, huggingface-hub
REM Portable: python path from arg1 or PYTHON env var or PATH

SET "SCRIPT_DIR=%~dp0"
SET "PYTHON_EXE=%~1"
IF "%PYTHON_EXE%"=="" SET "PYTHON_EXE=%PYTHON%"
IF "%PYTHON_EXE%"=="" SET "PYTHON_EXE=python"

cd /d "%SCRIPT_DIR%"
"%PYTHON_EXE%" -u "%SCRIPT_DIR%server.py"
