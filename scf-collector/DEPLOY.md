# 腾讯云 SCF 部署指南

## 流程概览

```
腾讯云 SCF（国内节点，每2小时触发）
    │
    ├─ 采集36氪/量子位/科委/经信局/海淀区等数据源
    ├─ 生成 data.json
    └─ 推送到 GitHub → Railway 自动部署
```

---

## 第一步：打包部署包

```bash
cd beijing-tech-hub\scf-collector
C:\Users\MR.Zhang\.workbuddy\binaries\python\envs\beijing-tech-hub\Scripts\python build_package.py
```

输出：`dist\scf-collector.zip`（约 3-5 MB）

---

## 第二步：创建云函数

1. 打开腾讯云控制台 → [云函数 SCF](https://console.cloud.tencent.com/scf)
2. 点击 **新建**
3. 配置：

   | 配置项 | 值 |
   |--------|-----|
   | 函数名称 | `jks-collector` |
   | 运行环境 | Python 3.12 |
   | 创建方式 | **上传 zip 包** |
   | 上传 | 上传 `dist\scf-collector.zip` |
   | 执行方法 | `handler.main_handler` |

4. 点击 **高级配置** → **环境变量**：

   | 键 | 值 |
   |----|-----|
   | `GITHUB_TOKEN` | `<YOUR_GITHUB_TOKEN>` |
   | `GITHUB_REPO` | `jingnian-1023/beijing-tech-hub` |

5. **超时时间**设为 **120 秒**（采集需要时间）
6. **内存**设为 **256 MB**
7. 点击 **完成**

---

## 第三步：配置定时触发器

1. 函数创建完成后，进入 **触发器管理** 页面
2. 点击 **创建触发器**
3. 配置：

   | 配置项 | 值 |
   |--------|-----|
   | 触发方式 | **定时触发器** |
   | 触发周期 | **自定义 Cron** |
   | Cron 表达式 | `0 0 */2 * * * *`（每 2 小时整点触发） |
   | 启用 | ✅ 是 |

4. 点击 **提交**

> Cron 说明：`0 0 */2 * * * *` = 每天 0点、2点、4点…22点执行

---

## 第四步：测试

1. 进入函数 **函数管理** → **函数代码** 页面
2. 点击 **测试**
3. 选择测试模板 `定时触发器`
4. 点击 **运行**
5. 等待 1-2 分钟（采集需要时间）
6. 验证日志显示：

   ```
   [1/3] Collected 41 items
   [2/3] Formatted 41 items to JSON (15.3 KB)
   [3/3] Successfully pushed data.json to GitHub
   ```

7. 检查 https://beijing-tech-hub-production.up.railway.app 是否更新

---

## 维护

### 查看日志
云函数控制台 → 函数 → **日志查询**

### 手动触发
控制台 → 函数 → **测试**（任意模板均可）

### 更新代码
本地改完后重新 `python build_package.py` → 控制台上传新 zip → 部署

---

## 费用

| 项目 | 用量（每月） | 免费额度 | 费用 |
|------|:-----------:|:--------:|:----:|
| 调用次数 | 360次（每2小时×30天） | 100万次 | ¥0 |
| 运行时间 | 360×2分钟 = 720分钟 | 1,000,000秒 ≈ 16,666分钟 | ¥0 |
| 网络流量 | 极小 | 免费额度内 | ¥0 |

**实际费用 = 0** ✅
