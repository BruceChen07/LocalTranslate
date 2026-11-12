# 模型目录

请将翻译模型文件放在本目录：

```
models/Hy-MT2-7B-Q4_K_M.gguf
```

下载地址（二选一）：

- ModelScope（国内快）：https://www.modelscope.cn/models/Tencent-Hunyuan/Hy-MT2-7B-GGUF
- Hugging Face：https://huggingface.co/tencent/Hy-MT2-7B-GGUF

推荐直接用脚本自动下载：

```bash
py -3.12 deploy.py              # 默认走 ModelScope
py -3.12 deploy.py --source hf  # 走 Hugging Face
```

如文件名不同，可用环境变量 `LT_MODEL` 指定，例如：

```
set LT_MODEL=Hy-MT2-7B-Q8_0.gguf
```
