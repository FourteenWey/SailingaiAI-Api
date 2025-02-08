from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *  # 导入事件类
import json
import os
import shutil
from datetime import datetime
import traceback
from pkg.core import entities as core_entities
import asyncio  

# 注册插件
@register(name="启航Ai-Api一键修改", description="一键修改API为启航AI", version="0.1", author="小馄饨")
class KeyConfigPlugin(BasePlugin):

    def __init__(self, host: APIHost):
        # 获取插件目录的路径
        plugin_dir = os.path.dirname(__file__)
        # 所有路径都基于插件目录
        self.config_path = os.path.join(plugin_dir, "provider.json")
        self.llm_models_source = os.path.join(plugin_dir, "llm-models.json")
        self.llm_models_target = "data/metadata/llm-models.json"
        self.user_states = {}  
        self.host = host
        
        # 确保目标目录存在
        os.makedirs(os.path.dirname(self.llm_models_target), exist_ok=True)
        
        # 如果源文件不存在，创建默认的llm-models.json
        if not os.path.exists(self.llm_models_source):
            default_models = {
                "list": [
                    {
                        "model_name": "gpt-3.5-turbo",
                        "name": "OneAPI/gpt-3.5-turbo",
                        "tool_call_supported": True,
                        "vision_supported": True
                    },
                    {
                        "model_name": "gpt-4",
                        "name": "OneAPI/gpt-4",
                        "tool_call_supported": True,
                        "vision_supported": True
                    }
                ]
            }
            with open(self.llm_models_source, 'w', encoding='utf-8') as f:
                json.dump(default_models, f, indent=4, ensure_ascii=False)
        
        # 确保目标文件存在（无论源文件是否刚创建）
        shutil.copy2(self.llm_models_source, self.llm_models_target)

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
        
        if msg == ".启航":
            help_msg = [
                "欢迎使用启航AI配置助手，请选择操作：",
                "1. 初始配置（配置API Key和模型）",
                "2. 修改模型",
                "\n请输入数字(1-2)选择操作"
            ]
            self.user_states[sender_id] = {
                'step': 0,  # 0表示选择操作阶段
                'api_url': "https://api.qhaigc.net/v1",  # 固定API URL
                'api_key': None,
                'model_name': None
            }
            ctx.add_return("reply", ["\n".join(help_msg)])
            ctx.prevent_default()
            return

        if msg == ".重载插件":
            try:
                await self.ap.reload(scope='plugin')
                ctx.add_return("reply", ["插件已重新加载"])
            except Exception as e:
                ctx.add_return("reply", [f"重载插件失败: {str(e)}"])
            ctx.prevent_default()
            return

        if msg == ".重载平台":
            try:
                await self.ap.reload(scope='platform')
                ctx.add_return("reply", ["消息平台已重新加载"])
            except Exception as e:
                ctx.add_return("reply", [f"重载平台失败: {str(e)}"])
            ctx.prevent_default()
            return

        if msg == ".重载LLM":
            try:
                await self.ap.reload(scope='provider')
                ctx.add_return("reply", ["LLM管理器已重新加载"])
            except Exception as e:
                ctx.add_return("reply", [f"重载LLM管理器失败: {str(e)}"])
            ctx.prevent_default()
            return
            
        if sender_id in self.user_states:
            current_state = self.user_states[sender_id]
            
            if current_state['step'] == 0:  # 处理选择操作
                ctx.prevent_default()
                if msg == "1":  # 初始配置
                    current_state['step'] = 2  # 直接从输入API Key开始
                    ctx.add_return("reply", ["步骤1: 请输入API Key\n(格式应为: sk-xxxxxxxx)\n如果你不知道API Key，请点击https://api.qhaigc.net/ 购买"])
                    return
                elif msg == "2":  # 修改模型
                    try:
                        with open(self.config_path, 'r', encoding='utf-8') as f:
                            current_config = json.load(f)
                        
                        current_state['step'] = 4  # 使用步骤4表示仅修改模型
                        current_state['api_url'] = current_config['requester']['openai-chat-completions']['base-url']
                        current_state['api_key'] = current_config['keys']['openai'][0]
                        ctx.add_return("reply", ["请输入新的模型名称\n(请输入API网站给的模型价格中的模型名称)\n如果你不知道模型名称，请点击https://api.qhaigc.net/pricing 查看"])
                        return
                    except Exception as e:
                        ctx.add_return("reply", ["读取当前配置失败，请先使用初始配置（选项1）完成完整配置。"])
                        del self.user_states[sender_id]
                        return
                else:
                    ctx.add_return("reply", ["无效的选择，请输入数字1-2选择操作：\n1. 初始配置（配置API Key和模型）\n2. 修改模型"])
                    return
            
            elif current_state['step'] == 2: 
                # 先阻止默认处理，防止消息发送给大模型
                ctx.prevent_default()
                
                if not msg.startswith('sk-'):
                    ctx.add_return("reply", ["API Key格式不正确，请重新输入\n(格式应为: sk-xxxxxxxx)\n如果你不知道API Key，请点击https://api.qhaigc.net/ 购买"])
                    return
                    
                current_state['api_key'] = msg.strip()
                current_state['step'] = 3
                ctx.add_return("reply", ["步骤2: 请输入模型名称\n(请输入API网站给的模型价格中的模型名称)\n如果你不知道模型名称，请点击https://api.qhaigc.net/pricing 查看"])
                return
                
            elif current_state['step'] == 3 or current_state['step'] == 4:  # 添加步骤4的处理
                # 先阻止默认处理，防止消息发送给大模型
                ctx.prevent_default()
                
                try:
                    # 1. 保存用户输入的模型名称
                    current_state['model_name'] = msg.strip()
                    
                    # 2. 创建备份
                    provider_backup = self.backup_file(self.config_path)
                    llm_models_backup = self.backup_file(self.llm_models_source)

                    # 3. 更新 provider.json
                    if not os.path.exists(self.config_path):
                        # 如果provider.json不存在，创建一个新的配置
                        config = {
                            "keys": {
                                "openai": [current_state['api_key']]
                            },
                            "requester": {
                                "openai-chat-completions": {
                                    "base-url": current_state['api_url']
                                }
                            },
                            "model": f"OneAPI/{current_state['model_name']}"
                        }
                    else:
                        with open(self.config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)

                    if current_state['step'] == 3:  # 完整配置时更新所有内容
                        config['keys']['openai'] = [current_state['api_key']]
                        config['requester']['openai-chat-completions']['base-url'] = current_state['api_url']
                    # 无论是哪个步骤都要更新模型名称
                    config['model'] = f"OneAPI/{current_state['model_name']}"

                    with open(self.config_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=4, ensure_ascii=False)
                        f.flush()
                        try:
                            os.fsync(f.fileno())
                        except Exception:
                            pass

                    # 4. 更新 llm-models.json
                    model_exists = False
                    if os.path.exists(self.llm_models_source):
                        with open(self.llm_models_source, 'r', encoding='utf-8') as f:
                            llm_models = json.load(f)
                        
                        for model in llm_models['list']:
                            if model.get('model_name') == current_state['model_name'] or model.get('name') == f"OneAPI/{current_state['model_name']}":
                                model_exists = True
                                break
                        
                        if not model_exists:
                            new_model = {
                                "model_name": current_state['model_name'],
                                "name": f"OneAPI/{current_state['model_name']}",
                                "tool_call_supported": True,
                                "vision_supported": True
                            }
                            llm_models['list'].append(new_model)
                        
                        # 无论是否添加新模型，都保存并复制到目标位置
                        with open(self.llm_models_source, 'w', encoding='utf-8') as f:
                            json.dump(llm_models, f, indent=4, ensure_ascii=False)
                            f.flush()
                            try:
                                os.fsync(f.fileno())
                            except Exception:
                                pass

                        # 确保目标目录存在并复制文件
                        os.makedirs(os.path.dirname(self.llm_models_target), exist_ok=True)
                        shutil.copy2(self.llm_models_source, self.llm_models_target)

                    # 5. 准备成功消息
                    success_msg = ["配置已更新成功！"]
                    if current_state['step'] == 4:  # 仅修改模型的消息
                        success_msg.extend([
                            f"1. 默认模型已更新为: OneAPI/{current_state['model_name']}",
                            "2. llm-models.json已更新" + (" (已添加新模型)" if not model_exists else "")
                        ])
                        if provider_backup:
                            success_msg.append(f"3. provider.json已备份为: {os.path.basename(provider_backup)}")
                        if llm_models_backup:
                            success_msg.append(f"4. llm-models.json已备份为: {os.path.basename(llm_models_backup)}")
                    else:  # 完整配置的消息
                        success_msg.extend([
                            "1. API Key已设置",
                            f"2. 默认模型已更新为: OneAPI/{current_state['model_name']}",
                            "3. llm-models.json已更新" + (" (已添加新模型)" if not model_exists else "")
                        ])
                        if provider_backup:
                            success_msg.append(f"4. provider.json已备份为: {os.path.basename(provider_backup)}")
                        if llm_models_backup:
                            success_msg.append(f"5. llm-models.json已备份为: {os.path.basename(llm_models_backup)}")

                    success_msg.append("\n请按以下步骤操作：")
                    success_msg.append("1. 关闭当前运行的langbot")
                    success_msg.append("2. 重新启动langbot（服务器用户在控制台输入 docker restart langbot）")
                    success_msg.append("3. 启动完成后即可开始聊天")

                    # 6. 发送成功消息并清理状态
                    ctx.add_return("reply", ["\n".join(success_msg)])
                    del self.user_states[sender_id]
                    
                    # 7. 创建一个异步任务来处理热重载
                    async def do_reload():
                        # 等待2秒确保消息发送完成
                        await asyncio.sleep(2)
                        try:
                            await self.ap.reload(scope='provider')
                            await self.ap.reload(scope='plugin')
                            await self.ap.reload(scope='platform')
                        except Exception as e:
                            # 如果重载失败，发送额外的错误消息
                            error_msg = [
                                f"\n⚠ 重载过程出现错误: {str(e)}",
                                "请尝试重启程序"
                            ]
                            ctx.add_return("reply", ["\n".join(error_msg)])
                    
                    # 8. 启动异步重载任务
                    asyncio.create_task(do_reload())

                except Exception as e:
                    error_msg = [
                        f"配置更新失败，错误信息：{str(e)}",
                        f"详细错误信息：\n{traceback.format_exc()}"
                    ]
                    if 'provider_backup' in locals() and provider_backup:
                        error_msg.append(f"您可以从备份文件恢复: {os.path.basename(provider_backup)}")
                    ctx.add_return("reply", ["\n".join(error_msg)])
                    del self.user_states[sender_id]
                    ctx.prevent_default()
            
            else:
                ctx.prevent_default()

    @handler(GroupNormalMessageReceived)
    async def group_normal_message_received(self, ctx: EventContext):
        msg = ctx.event.text_message
        if msg.startswith(".一键修改") or msg.startswith("sk-"):
            ctx.add_return("reply", ["为了保护您的API key安全，请私聊机器人进行配置修改。"])
            ctx.prevent_default()

    def __del__(self):
        pass
