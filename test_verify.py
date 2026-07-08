"""Antigravity Web 全量验证脚本"""
import json
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = "c:/code/antigravity-web/test-screenshots"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    print("=" * 60)
    print("1. 测试仪表盘页面（Dashboard）")
    print("=" * 60)
    page.goto("http://localhost:5174/")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.screenshot(path=f"{SCREENSHOT_DIR}/01-dashboard.png", full_page=True)
    
    # 检查空数据提示
    alert = page.locator(".el-alert").all()
    print(f"  空数据提示 el-alert 数量: {len(alert)}")
    if alert:
        print(f"  提示文本: {alert[0].inner_text()[:100]}")
    
    # 检查统计卡片
    stats = page.locator(".el-statistic").all()
    print(f"  统计卡片数量: {len(stats)}")
    for s in stats:
        print(f"    - {s.inner_text().strip()}")

    print("\n" + "=" * 60)
    print("2. 测试账号管理页面（Accounts）")
    print("=" * 60)
    page.goto("http://localhost:5174/accounts")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.screenshot(path=f"{SCREENSHOT_DIR}/02-accounts.png", full_page=True)
    
    empty_rows = page.locator(".el-table__empty-text").all()
    print(f"  空表格提示: {empty_rows[0].inner_text() if empty_rows else 'N/A'}")
    
    # 检查添加按钮
    add_btns = page.locator("button:has-text('添加')").all()
    print(f"  添加按钮: {len(add_btns)} 个")
    import_btns = page.locator("button:has-text('导入')").all()
    print(f"  导入按钮: {len(import_btns)} 个")

    print("\n" + "=" * 60)
    print("3. 测试签到页面（Checkin）")
    print("=" * 60)
    page.goto("http://localhost:5174/checkin")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.screenshot(path=f"{SCREENSHOT_DIR}/03-checkin.png", full_page=True)
    empty_rows = page.locator(".el-table__empty-text").all()
    print(f"  空表格提示: {empty_rows[0].inner_text() if empty_rows else 'N/A'}")

    print("\n" + "=" * 60)
    print("4. 测试 API 代理页面（ApiProxy）")
    print("=" * 60)
    page.goto("http://localhost:5174/proxy")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.screenshot(path=f"{SCREENSHOT_DIR}/04-proxy-status.png", full_page=True)
    
    # 检查代理状态
    tags = page.locator(".el-tag").all()
    print(f"  状态标签数量: {len(tags)}")
    for t in tags[:5]:
        print(f"    - {t.inner_text().strip()}")
    
    # 测试各 Tab
    tabs = ["上游Key管理", "子Key管理", "请求日志", "使用统计", "模型列表"]
    for i, tab_name in enumerate(tabs):
        print(f"\n  --- Tab {i+1}: {tab_name} ---")
        page.locator(f".el-tabs__item:has-text('{tab_name}')").click()
        time.sleep(1)
        page.screenshot(path=f"{SCREENSHOT_DIR}/05-proxy-tab{i+1}-{tab_name}.png", full_page=True)
        
        if tab_name == "上游Key管理":
            empty = page.locator(".el-table__empty-text").all()
            print(f"    空表格: {empty[0].inner_text() if empty else 'N/A'}")
            add_btn = page.locator("button:has-text('添加上游Key')").all()
            print(f"    添加按钮: {len(add_btn)}")
            
        elif tab_name == "子Key管理":
            empty = page.locator(".el-table__empty-text").all()
            print(f"    空表格: {empty[0].inner_text() if empty else 'N/A'}")
            add_btn = page.locator("button:has-text('创建子Key')").all()
            print(f"    创建按钮: {len(add_btn)}")
            
        elif tab_name == "请求日志":
            # 检查日志文件列表
            log_table = page.locator(".el-table").all()
            print(f"    表格数量: {len(log_table)}")
            rows = page.locator(".el-table__row").all()
            print(f"    日志文件行数: {len(rows)}")
            # 检查实时刷新开关
            switches = page.locator(".el-switch").all()
            print(f"    开关数量: {len(switches)}")
            # 检查日志内容区域
            pre = page.locator("pre").all()
            print(f"    日志内容区(pre): {len(pre)}")
            
        elif tab_name == "使用统计":
            cards = page.locator(".el-card").all()
            print(f"    统计卡片数量: {len(cards)}")
            stats = page.locator(".el-statistic").all()
            print(f"    统计数值数量: {len(stats)}")
            for s in stats[:6]:
                print(f"      - {s.inner_text().strip()}")
            # 检查周期选择器
            selects = page.locator(".el-select").all()
            print(f"    选择器数量: {len(selects)}")
            
        elif tab_name == "模型列表":
            # 检查搜索框
            search = page.locator("input[placeholder*='搜索'], input[placeholder*='过滤']").all()
            print(f"    搜索框: {len(search)}")
            # 检查表格
            rows = page.locator(".el-table__row").all()
            print(f"    模型行数: {len(rows)}")
            if rows:
                first_row = rows[0].inner_text()
                print(f"    第一行: {first_row[:80]}")

    print("\n" + "=" * 60)
    print("5. 测试设置页面（Settings）")
    print("=" * 60)
    page.goto("http://localhost:5174/settings")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.screenshot(path=f"{SCREENSHOT_DIR}/06-settings.png", full_page=True)
    
    # 检查数据管理区域
    cards = page.locator(".el-card").all()
    print(f"  卡片数量: {len(cards)}")
    for c in cards:
        header = c.locator(".el-card__header").all()
        if header:
            print(f"    - {header[0].inner_text().strip()}")
    
    # 检查导出按钮
    export_btns = page.locator("button:has-text('导出')").all()
    print(f"  导出按钮: {len(export_btns)}")
    # 检查导入按钮
    import_btns = page.locator("button:has-text('导入')").all()
    print(f"  导入按钮: {len(import_btns)}")
    # 检查上传组件
    uploads = page.locator(".el-upload").all()
    print(f"  上传组件: {len(uploads)}")

    print("\n" + "=" * 60)
    print("6. 测试侧边栏导航")
    print("=" * 60)
    page.goto("http://localhost:5174/")
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    menu_items = page.locator(".el-menu-item").all()
    print(f"  菜单项数量: {len(menu_items)}")
    for item in menu_items:
        print(f"    - {item.inner_text().strip()}")

    print("\n" + "=" * 60)
    print("7. 测试添加上游 Key 对话框")
    print("=" * 60)
    page.goto("http://localhost:5174/proxy")
    page.wait_for_load_state("networkidle")
    time.sleep(0.5)
    page.locator(".el-tabs__item:has-text('上游Key管理')").click()
    time.sleep(0.5)
    page.locator("button:has-text('添加上游Key')").click()
    time.sleep(0.5)
    page.screenshot(path=f"{SCREENSHOT_DIR}/07-add-key-dialog.png", full_page=True)
    
    dialog = page.locator(".el-dialog").all()
    print(f"  对话框数量: {len(dialog)}")
    form_items = page.locator(".el-form-item").all()
    print(f"  表单项数量: {len(form_items)}")
    for fi in form_items:
        label = fi.locator(".el-form-item__label").all()
        if label:
            print(f"    - {label[0].inner_text().strip()}")
    
    # 关闭对话框
    page.locator(".el-dialog button:has-text('取消')").click()
    time.sleep(0.5)

    print("\n" + "=" * 60)
    print("8. 测试创建子 Key 对话框")
    print("=" * 60)
    page.locator(".el-tabs__item:has-text('子Key管理')").click()
    time.sleep(0.5)
    page.locator("button:has-text('创建子Key')").click()
    time.sleep(0.5)
    page.screenshot(path=f"{SCREENSHOT_DIR}/08-add-subkey-dialog.png", full_page=True)
    
    form_items = page.locator(".el-dialog .el-form-item").all()
    print(f"  表单项数量: {len(form_items)}")
    for fi in form_items:
        label = fi.locator(".el-form-item__label").all()
        if label:
            print(f"    - {label[0].inner_text().strip()}")
    
    page.locator(".el-dialog button:has-text('取消')").click()
    time.sleep(0.5)

    print("\n" + "=" * 60)
    print("验证完成！截图已保存到 test-screenshots/")
    print("=" * 60)
    
    browser.close()
