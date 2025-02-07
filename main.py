from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *  
import json
import os
import shutil
from datetime import datetime
import traceback

# 注册插件
@register(name="启航api", description="一键修改API配置", version="0.1", author="小馄饨")
class KeyConfigPlugin(BasePlugin):

    def __init__(self, host: APIHost):
        self.config_path = "data/config/provider.json"
        self.llm_models_source = "plugins/key/llm-models.json"
        self.llm_models_target = "data/metadata/llm-models.json"
        self.waiting_for_key = {}  # 用于记录等待输入key的用户
        self.host = host
        
    async def initialize(self):
        pass

    def backup_file(self, file_path):
        """创建文件备份"""
        try:
            if os.path.exists(file_path):
                backup_path = f"{file_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                shutil.copy2(file_path, backup_path)
                return backup_path
            return None
        except Exception as e:
            raise

    @handler(PersonNormalMessageReceived)
    async def person_normal_message_received(self, ctx: EventContext):
        msg = ctx.event.text_message
        sender_id = ctx.event.sender_id
        
        if msg == "/一键修改":
            self.waiting_for_key[sender_id] = True
            ctx.add_return("reply", ["请输入正确的API key，格式应为: sk-xxxxxxxx"])
            ctx.prevent_default()
            return
            
        if sender_id in self.waiting_for_key:
            # 用户正在输入API key
            if not msg.startswith("sk-"):
                ctx.add_return("reply", ["输入的API key格式不正确，请重新输入，格式应为: sk-xxxxxxxx"])
                ctx.prevent_default()
                return
                
            api_key = msg.strip()
            del self.waiting_for_key[sender_id]  # 清除等待状态

            try:
                # 创建配置文件备份
                provider_backup = self.backup_file(self.config_path)
                llm_models_backup = self.backup_file(self.llm_models_target)

                # 读取现有配置
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                # 更新配置
                config['keys']['openai'] = [api_key]
                config['requester']['openai-chat-completions']['base-url'] = "https://ai.thelazy.top/v1"
                config['model'] = "OneAPI/deepseek-r1"

                # 保存更新后的配置
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except Exception:
                        pass

                # 复制llm-models.json文件
                success_msg = ["配置已更新成功！"]
                if os.path.exists(self.llm_models_source):
                    shutil.copy2(self.llm_models_source, self.llm_models_target)
                    success_msg.extend([
                        "1. API key已设置",
                        "2. 默认模型已更新为deepseek-r1",
                        "3. llm-models.json已更新"
                    ])
                    if provider_backup:
                        success_msg.append(f"4. provider.json已备份为: {os.path.basename(provider_backup)}")
                    if llm_models_backup:
                        success_msg.append(f"5. llm-models.json已备份为: {os.path.basename(llm_models_backup)}")
                else:
                    success_msg.extend([
                        "1. API key已设置",
                        "2. 默认模型已更新为deepseek-r1",
                        "注意：未找到llm-models.json文件，请检查文件是否存在"
                    ])
                    if provider_backup:
                        success_msg.append(f"3. provider.json已备份为: {os.path.basename(provider_backup)}")
                
                success_msg.append("\n请按以下步骤操作：")
                success_msg.append("1. 关闭当前运行的langbot")
                success_msg.append("2. 重新启动langbot（服务器用户在控制台输入 docker restart langbot）")
                success_msg.append("3. 启动完成后即可开始聊天")

                ctx.add_return("reply", ["\n".join(success_msg)])

            except Exception as e:
                error_msg = [
                    f"配置更新失败，错误信息：{str(e)}",
                    f"详细错误信息：\n{traceback.format_exc()}"
                ]
                if 'provider_backup' in locals() and provider_backup:
                    error_msg.append(f"您可以从备份文件恢复: {os.path.basename(provider_backup)}")
                ctx.add_return("reply", ["\n".join(error_msg)])

            ctx.prevent_default()

    @handler(GroupNormalMessageReceived)
    async def group_normal_message_received(self, ctx: EventContext):
        msg = ctx.event.text_message
        if msg.startswith("/一键修改") or msg.startswith("sk-"):
            ctx.add_return("reply", ["为了保护您的API key安全，请私聊机器人进行配置修改。"])
            ctx.prevent_default()

    def __del__(self):
        pass
