# 项目文件操作约束

以下约束来自项目维护者。

禁止批量删除文件或目录。

不要使用：

- `del /s`
- `rd /s`
- `rmdir /s`
- `Remove-Item -Recurse`
- `rm -rf`

需要删除文件时，只能一次删除一个明确路径的文件。例如：

```powershell
Remove-Item -LiteralPath 'C:\path\to\file.txt'
```

如果需要批量删除文件，应停止该删除操作，并请求用户手动处理。
