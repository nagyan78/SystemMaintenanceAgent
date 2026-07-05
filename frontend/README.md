# 前端工作台

Vue 3 + Vite 实现的本地工作台框架。当前已接通 Excel 上传链路：

- `POST /api/files/upload`
- `GET /api/files`

开发服务会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 启动

```bash
npm install
npm run dev
```

打开上传页：

```text
http://127.0.0.1:5173/upload
```

后端需先启动：

```bash
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
