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
        self.config_path = "data/config/provider.json"
        self.llm_models_source = "plugins/SailingaiAI-Api/llm-models.json"
        self.llm_models_target = "data/metadata/llm-models.json"
        self.user_states = {}  
        self.host = host
        self.fixed_api_url = "https://api.qhaigc.net/v1"  # Add fixed API URL
        
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
                "欢迎使用启航AI-Api配置助手，请选择操作：",
                "1. 初始配置（配置API Key和模型）",
                "2. 修改模型",
                "\n请输入数字(1-2)选择操作"
            ]
            self.user_states[sender_id] = {
                'step': 0,  # 0表示选择操作阶段
                'api_key': None,
                'model_name': None
            }
            ctx.add_return("reply", ["\n".join(help_msg)])
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
                        current_state['api_key'] = current_config['keys']['openai'][0]
                        ctx.add_return("reply", ["请输入新的模型名称\n(请输入API网站给的模型价格中的模型名称)\n如果你不知道模型名称，请点击 https://api.qhaigc.net/pricing 查看"])
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
                    ctx.add_return("reply", ["API Key格式不正确，请重新输入\n(格式应为: sk-xxxxxxxx)\n如果你不知道API Key，请点击https://api.qhaigc.net/ 购买API Key"])
                    return
                    
                current_state['api_key'] = msg.strip()
                current_state['step'] = 3
                ctx.add_return("reply", ["步骤3: 请输入模型名称\n(请输入API网站给的模型价格中的模型名称)\n如果你不知道模型名称，请点击 https://api.qhaigc.net/pricing 查看"])
                return
                
            elif current_state['step'] == 3 or current_state['step'] == 4:  # 添加步骤4的处理
                # 先阻止默认处理，防止消息发送给大模型
                ctx.prevent_default()
                
                try:
                    # 1. 保存用户输入的模型名称
                    current_state['model_name'] = msg.strip()
                    model_name = f"OneAPI/{current_state['model_name']}"
                    
                    # 2. 创建备份
                    provider_backup = self.backup_file(self.config_path)
                    llm_models_backup = self.backup_file(self.llm_models_target)

                    # 3. 先处理 llm-models.json
                    model_exists = False
                    new_model = {
                        "model_name": current_state['model_name'],
                        "name": model_name,
                        "tool_call_supported": True,
                        "vision_supported": True
                    }

                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(self.llm_models_target), exist_ok=True)

                    try:
                        # 读取现有的模型列表
                        target_models = {"list": []}
                        if os.path.exists(self.llm_models_target):
                            try:
                                with open(self.llm_models_target, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                    if content.strip():
                                        target_models = json.loads(content)
                                    if 'list' not in target_models:
                                        target_models = {"list": []}
                            except json.JSONDecodeError:
                                target_models = {"list": []}
                        
                        # 分离 OneAPI 和非 OneAPI 模型
                        model_list = target_models.get('list', [])
                        oneapi_models = [model for model in model_list if model.get('name', '').startswith('OneAPI/')]
                        other_models = [model for model in model_list if not model.get('name', '').startswith('OneAPI/')]
                        
                        # 检查新模型是否已存在于 OneAPI 模型中
                        model_exists = any(model.get('name') == model_name for model in oneapi_models)
                        
                        if not model_exists:
                            # 将新的 OneAPI 模型添加到 OneAPI 模型列表开头
                            oneapi_models.insert(0, new_model)
                            # 合并 OneAPI 模型和其他模型
                            target_models['list'] = oneapi_models + other_models

                            # 写入更新后的配置
                            temp_file = f"{self.llm_models_target}.temp"
                            try:
                                with open(temp_file, 'w', encoding='utf-8') as f:
                                    json.dump(target_models, f, indent=4, ensure_ascii=False)
                                    f.flush()
                                    os.fsync(f.fileno())
                                
                                if os.path.exists(self.llm_models_target):
                                    os.remove(self.llm_models_target)
                                os.rename(temp_file, self.llm_models_target)
                            except Exception as e:
                                if os.path.exists(temp_file):
                                    os.remove(temp_file)
                                raise Exception(f"写入llm-models.json失败: {str(e)}")

                    except Exception as e:
                        # 添加更详细的错误信息
                        error_details = f"更新llm-models.json失败: {str(e)}\n"
                        error_details += f"目标文件: {self.llm_models_target}\n"
                        error_details += f"新模型: {json.dumps(new_model, ensure_ascii=False)}\n"
                        error_details += f"堆栈跟踪:\n{traceback.format_exc()}"
                        raise Exception(error_details)

                    # 4. 然后处理 provider.json
                    try:
                        with open(self.config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)

                        if current_state['step'] == 3:  # 完整配置时更新所有内容
                            if 'keys' not in config:
                                config['keys'] = {}
                            if 'openai' not in config['keys']:
                                config['keys']['openai'] = []
                            config['keys']['openai'] = [current_state['api_key']]
                            
                            if 'requester' not in config:
                                config['requester'] = {'openai-chat-completions': {}}
                            if 'openai-chat-completions' not in config['requester']:
                                config['requester']['openai-chat-completions'] = {}
                            config['requester']['openai-chat-completions']['base-url'] = self.fixed_api_url

                        # 更新模型名称
                        config['model'] = model_name

                        # 保存provider.json
                        with open(self.config_path, 'w', encoding='utf-8') as f:
                            json.dump(config, f, indent=4, ensure_ascii=False)
                            f.flush()
                            os.fsync(f.fileno())
                    except Exception as e:
                        raise Exception(f"更新provider.json失败: {str(e)}")
                    
                    # 5. 准备成功消息
                    success_msg = ["配置已更新成功！"]
                    if current_state['step'] == 4:  # 仅修改模型的消息
                        if os.path.exists(self.llm_models_target):
                            success_msg.extend([
                                f"1. 默认模型已更新为: OneAPI/{current_state['model_name']}",
                                "2. llm-models.json已更新" + (" (已添加新模型)" if not os.path.exists(self.llm_models_target) else "")
                            ])
                            if provider_backup:
                                success_msg.append(f"3. provider.json已备份为: {os.path.basename(provider_backup)}")
                            if llm_models_backup:
                                success_msg.append(f"4. llm-models.json已备份为: {os.path.basename(llm_models_backup)}")
                    else:  # 完整配置的消息
                        if os.path.exists(self.llm_models_target):
                            success_msg.extend([
                                "1. API Key已设置",
                                f"2. 默认模型已更新为: OneAPI/{current_state['model_name']}",
                                "3. llm-models.json已更新" + (" (已添加新模型)" if not os.path.exists(self.llm_models_target) else "")
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
        if msg.startswith(".模型配置") or msg.startswith("sk-"):
            ctx.add_return("reply", ["为了保护您的API key安全，请私聊机器人进行配置修改。"])
            ctx.prevent_default()

    def __del__(self):
        pass
