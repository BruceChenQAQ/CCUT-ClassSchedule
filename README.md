# 项目介绍
详见 https://brucec.cn/2022/03/09/CCUT-ClassSchedule/

# 如何构建
1. 前端部分
   * 官方文档 https://tailwindcss.com/docs/installation
   * 开发 index.html 或 templete.html 时需修改 tailwind.config.js 中的 content
   * 开发时使用```npx tailwindcss -i ./input.css -o ./output.css --watch```可自动构建 output.css 用于开发
   * 为生产环境优化使用 ```npx tailwindcss -o build.css --minify```
2. Mirai插件部分
   * [mirai仓库地址](https://github.com/mamoe/mirai)
   * [mirai-console 开发文档](https://github.com/mamoe/mirai-console/tree/master/docs)
   * [配置 Mirai Console 项目](https://github.com/mamoe/mirai-console/blob/master/docs/ConfiguringProjects.md)
   * [适用于新人的 mirai 帮助文档](https://mirai.mamoe.net/topic/802/%E9%80%82%E7%94%A8%E4%BA%8E%E6%96%B0%E4%BA%BA%E7%9A%84-mirai-%E5%B8%AE%E5%8A%A9%E6%96%87%E6%A1%A3-%E5%A4%87%E4%BB%BD)

# 项目结构
```
│  ClassSchedule.db                             # Sqlite数据库(仅含表结构)
│  index.py                                     # 爬虫和API服务器部分
│                                               #
├─CaptchaImgs                                   # 用于测试的验证码图片
│                                               #
├─htmlDevelop                                   # 前端页面开发
│  │  build.css                                 # 构建用于生产环境的CSS
│  │  index.html                                # 查询页面(首页)
│  │  input.css                                 # Tailwind CSS 配置
│  │  output.css                                # 构建用于开发环境的CSS
│  │  package-lock.json                         # NPM依赖包配置
│  │  package.json                              # NPM依赖包配置
│  │  Tailwind Develop build.bat                # 用于开发环境构建
│  │  Tailwind Installation.bat                 # 安装依赖
│  │  Tailwind Production build.bat             # 用于生产环境构建
│  │  tailwind.config.js                        # Tailwind CSS 构建配置
│  │  templete.html                             # 个人课程表模板页面
│  │                                            #
│  └─node_modules                               # NPM模组
│                                               #
├─logs                                          # index.py日志记录
│                                               #
├─Pages                                         # Nginx根文件夹
│  │  index.html                                # 查询页面(首页)
│  │                                            #
│  └─images                                     # 图像文件
│          login_background.avif                # 首页背景图片
│                                               #
├─pluginDevelop                                 # Mirai插件(IDEA项目)
│  │                                            #
│  ├─build                                      # 构建结果
│  │  │                                         #
│  │  └─mirai                                   #
│  │         course_timetable-1.0.mirai.jar     #
│  │                                            #
│  └─src                                        #
│      ├─main                                   #
│      │  ├─kotlin                              #
│      │  │      CourseTimetable.kt             # 主要的插件代码
│      │  │                                     #
│      │  └─resources                           #
│      │                                        #
│      └─test                                   #
│                                               #
└─ThirdParty                                    # 第三方库(pypi仓库下架了)
    └─muggle_ocr                                #
```

# 目前存在的问题
* Mirai插件的代码较为混乱，需要重新整理并划分模块
* 在获取Bot示例时，修改为先获取列表在选择一个实例(现在写死了QQ号)
* 将爬虫改为单独线程，通过两个队列与其他线程(WebSocket监听线程、Flask线程)交互，更好的限制访问教务系统的QPS，但这可能会引起绑定/查询操作延迟升高