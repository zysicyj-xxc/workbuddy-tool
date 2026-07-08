"""浏览器全量验证脚本 - 验证重构后的所有页面和功能

验证项：
1. 左侧菜单 6 项（仪表盘/账号管理/每日签到/API代理/日志/数据管理）
2. 左下角外观切换（深色/浅色）
3. API代理页 5 个 Tab（账号管理/子Key管理/资源包管理/使用统计/模型列表）
4. 日志页（文件列表 + 内容预览 + 实时刷新开关）
5. 数据管理页（导出 + 导入旧版 + 导入加密）
6. 无"关于"卡片
7. 无"代理设置"卡片（在数据管理页）
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5174"
PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"[PASS] {msg}")


def fail(msg):
    global FAIL
    FAIL += 1
    print(f"[FAIL] {msg}")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # ─── 1. 首页加载 ───
        page.goto(BASE)
        page.wait_for_load_state("networkidle")
        title = page.title()
        if "Antigravity" in title:
            ok(f"首页加载成功，title={title}")
        else:
            fail(f"首页加载异常，title={title}")

        # ─── 2. 左侧菜单项验证 ───
        menu_items = page.locator(".el-menu-item").all()
        menu_texts = [m.inner_text().strip() for m in menu_items]
        expected_menus = ["仪表盘", "账号管理", "每日签到", "API代理", "日志", "数据管理"]
        for em in expected_menus:
            if any(em in t for t in menu_texts):
                ok(f"菜单项存在：{em}")
            else:
                fail(f"菜单项缺失：{em}（实际菜单：{menu_texts}）")
        # 验证"设置"已改名
        if any("设置" == t.strip() for t in menu_texts):
            fail("菜单仍为'设置'，未改名为'数据管理'")
        else:
            ok("菜单'设置'已改名为'数据管理'")

        # ─── 3. 左下角外观切换 ───
        theme_switch = page.locator(".aside-footer .el-switch").first
        if theme_switch.is_visible():
            ok("左下角外观切换存在")
            # 点击切换深色
            theme_switch.click()
            page.wait_for_timeout(500)
            html_class = page.evaluate("document.documentElement.className")
            if "dark" in html_class:
                ok("深色模式切换成功")
            else:
                fail(f"深色模式切换失败，html class={html_class}")
            # 切回浅色
            theme_switch.click()
            page.wait_for_timeout(500)
            ok("切换回浅色模式")
        else:
            fail("左下角外观切换未找到")

        # ─── 4. 仪表盘 ───
        page.goto(f"{BASE}/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        if page.locator("text=尚未导入账号数据").count() > 0 or page.locator(".el-card").count() > 0:
            ok("仪表盘渲染正常（空数据提示或卡片）")
        else:
            fail("仪表盘渲染异常")

        # ─── 5. API代理页 - Tab 验证 ───
        page.goto(f"{BASE}/proxy")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        # 代理服务状态卡片
        if page.locator("text=代理服务状态").count() > 0:
            ok("API代理页：代理服务状态卡片存在")
        else:
            fail("API代理页：代理服务状态卡片缺失")

        # Tab 标签
        tabs = page.locator(".el-tabs__item").all()
        tab_texts = [t.inner_text().strip() for t in tabs]
        expected_tabs = ["账号管理", "子Key管理", "资源包管理", "使用统计", "模型列表"]
        for et in expected_tabs:
            if any(et in t for t in tab_texts):
                ok(f"API代理 Tab 存在：{et}")
            else:
                fail(f"API代理 Tab 缺失：{et}（实际：{tab_texts}）")
        # 验证"上游Key管理"已改名
        if any("上游Key" in t for t in tab_texts):
            fail("Tab 仍为'上游Key管理'，未改名为'账号管理'")
        else:
            ok("Tab'上游Key管理'已改名为'账号管理'")
        # 验证"请求日志"Tab 已移除
        if any("请求日志" in t for t in tab_texts):
            fail("请求日志 Tab 仍存在于 API代理页")
        else:
            ok("请求日志 Tab 已从 API代理页移除")

        # 点击资源包管理 Tab
        pkg_tab = page.locator(".el-tabs__item", has_text="资源包管理").first
        if pkg_tab.count() > 0:
            pkg_tab.click()
            page.wait_for_timeout(1000)
            # 资源包管理提示
            if page.locator("text=按到期时间升序排列").count() > 0:
                ok("资源包管理：排序提示存在")
            else:
                fail("资源包管理：排序提示缺失")
            # 空数据提示
            if page.locator("text=暂无资源包数据").count() > 0:
                ok("资源包管理：空数据提示正常")
            else:
                fail("资源包管理：空数据提示缺失")

        # ─── 6. 日志页 ───
        page.goto(f"{BASE}/logs")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        if page.locator("text=日志文件").count() > 0:
            ok("日志页：日志文件列表存在")
        else:
            fail("日志页：日志文件列表缺失")
        if page.locator("text=实时刷新").count() > 0:
            ok("日志页：实时刷新开关存在")
        else:
            fail("日志页：实时刷新开关缺失")
        # 检查是否有日志文件
        log_rows = page.locator(".el-table__row").count()
        if log_rows > 0:
            ok(f"日志页：有 {log_rows} 个日志文件")
            # 点击第一个日志文件
            page.locator(".el-table__row").first.click()
            page.wait_for_timeout(1500)
            if page.locator(".log-content").count() > 0:
                ok("日志页：点击文件后显示内容预览")
            else:
                fail("日志页：点击文件后未显示内容预览")
        else:
            ok("日志页：暂无日志文件（可接受）")

        # ─── 7. 数据管理页 ───
        page.goto(f"{BASE}/settings")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        if page.locator("text=数据管理").count() > 0:
            ok("数据管理页：标题存在")
        else:
            fail("数据管理页：标题缺失")
        if page.locator("text=导出加密数据包").count() > 0:
            ok("数据管理页：导出按钮存在")
        else:
            fail("数据管理页：导出按钮缺失")
        if page.locator("text=导入 SQLite 数据包").count() > 0:
            ok("数据管理页：导入旧版按钮存在")
        else:
            fail("数据管理页：导入旧版按钮缺失")
        if page.locator("text=导入加密数据包").count() > 0:
            ok("数据管理页：导入加密按钮存在")
        else:
            fail("数据管理页：导入加密按钮缺失")
        # 验证"代理设置"卡片已移除
        if page.locator("text=代理设置").count() > 0:
            fail("数据管理页：仍存在'代理设置'卡片（应已移除）")
        else:
            ok("数据管理页：'代理设置'卡片已移除")
        # 验证"关于"卡片已移除
        if page.locator("text=关于").count() > 0:
            fail("数据管理页：仍存在'关于'卡片（应已移除）")
        else:
            ok("数据管理页：'关于'卡片已移除")
        # 验证"外观"卡片已移除（移到左下角了）
        if page.locator(".el-card").filter(has_text="外观").count() > 0:
            fail("数据管理页：仍存在'外观'卡片（应已移至左下角）")
        else:
            ok("数据管理页：'外观'卡片已移除（已移至左下角）")

        # ─── 8. 账号管理页（原有功能仍正常） ───
        page.goto(f"{BASE}/accounts")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        if page.locator(".el-card").count() > 0:
            ok("账号管理页渲染正常")
        else:
            fail("账号管理页渲染异常")

        # ─── 9. 每日签到页 ───
        page.goto(f"{BASE}/checkin")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        if page.locator(".el-card").count() > 0:
            ok("每日签到页渲染正常")
        else:
            fail("每日签到页渲染异常")

        # ─── 10. 深色模式下页面渲染 ───
        # 切换深色
        theme_switch = page.locator(".aside-footer .el-switch").first
        theme_switch.click()
        page.wait_for_timeout(800)
        # 截图深色模式
        page.goto(f"{BASE}/proxy")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path="c:/code/antigravity-web/screenshot_dark.png", full_page=True)
        ok("深色模式截图已保存")
        # 切回
        theme_switch = page.locator(".aside-footer .el-switch").first
        theme_switch.click()
        page.wait_for_timeout(500)

        browser.close()

    print(f"\n{'='*50}")
    print(f"验证结果：{PASS} 通过，{FAIL} 失败")
    print(f"{'='*50}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(run())
