from src.plugin_system import register_plugin, ConfigField, BasePlugin
from src.chat.utils.prompt_builder import Prompt, global_prompt_manager
from src.common.logger import get_logger
import textwrap

# --- Prompt Templates (常量区) ---

ACTION_REPLY = textwrap.dedent("""
    reply
    动作描述：
    进行回复，你可以自然的顺着正在进行的聊天内容进行回复或自然的提出一个问题
    {{
        "action": "reply",
        "target_message_id":"想要回复的消息id",
        "reason":"回复的原因"
    }}
""")

ACTION_COMPLETE_TALK = textwrap.dedent("""
    complete_talk
    动作描述：
    当前聊天暂时结束了，对方离开，没有更多话题了
    你可以使用该动作来暂时休息，等待对方有新发言再继续：
    - %s
    - 聊天内容显示当前聊天已经结束或者没有新内容时候，选择complete_talk
    选择此动作后，将不再继续循环思考，直到收到对方的新消息
    {{
        "action": "complete_talk",
        "target_message_id":"触发完成对话的消息id（通常是对方的最新消息）",
        "reason":"选择完成对话的原因"
    }}
""")

ACTION_WAIT_ENHANCED = textwrap.dedent("""
    wait
    动作描述：
    暂时不再发言，等待指定时间。适用于以下情况：
    - 你已经表达清楚一轮，想给对方留出空间
    - 你感觉对方的话还没说完，或者自己刚刚发了好几条连续消息
    - 你想要等待一定时间来让对方把话说完，或者等待对方反应
    - 你想保持安静，专注"听"而不是马上回复
    {{
        "action": "wait",
        "target_message_id":"想要作为这次等待依据的消息id（通常是对方的最新消息）",
        "reason":"选择等待的原因"
    }}
""")

PLANNER_TEMPLATE = """
{time_block}
{name_block}
{chat_context_description}，以下是具体的聊天内容

**聊天内容**
{chat_content_block}

**动作记录**
{actions_before_now_block}

**可用的action**
{action_blocks}

{action_options_text}

请选择合适的action，并说明触发action的消息id和选择该action的原因。消息id格式:m+数字
先输出你的选择思考理由，再输出你选择的action，理由是一段平文本，不要分点，精简。
**动作选择要求**
请你根据聊天内容,用户的最新消息和以下标准选择合适的动作:
{plan_style}
{moderation_prompt}

请选择所有符合使用要求的action，动作用json格式输出，如果输出多个json，每个json都要单独用BBBjson包裹，你可以重复使用同一个动作或不同动作:
**示例**
// 理由文本
```json
{{
    "action":"动作名",
    "target_message_id":"触发动作的消息id",
    //对应参数
}}
```
"""

ACTION_TEMPLATE = """
{action_name}
动作描述：{action_description}
使用条件：
{action_require}
{{
    "action": "{action_name}",{action_parameters},
    "target_message_id":"触发action的消息id",
    "reason":"触发action的原因"
}}
"""

@register_plugin
class Plugin(BasePlugin):
    plugin_name = "wait_remover"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"
    config_schema = {
        "plugin": {
            "config_version": ConfigField(type=str, default="1.0.2", description="配置版本(不要修改)"),
            "change_wait_action": ConfigField(type=bool, default=True, description="改善wait动作(推荐)"),
            "remove_wait_action": ConfigField(type=bool, default=False, description="移除私聊的wait动作"),
        }
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = get_logger(self.plugin_name)
        self.is_remove = self.get_config("plugin.remove_wait_action")
        self.is_enhance = self.get_config("plugin.change_wait_action")
        
        # 直接同步执行 Patch
        self.patch_planner()

    def patch_planner(self):
        """
        直接修改 global_prompt_manager 中的缓存对象，无需 Hook 原函数
        """
        if not self.is_remove and not self.is_enhance:
            return
        
        self.logger.info(f"正在应用 wait_remover 补丁 (Remove: {self.is_remove}, Enhance: {self.is_enhance})...")
        
        try:
            # 构建新的 action 列表
            action_list = [ACTION_REPLY]
            
            if self.is_remove:
                complete_note = "聊天内容显示当前聊天已经结束或者没有新内容时候，选择complete_talk"
            else:
                complete_note = "多次wait之后，对方迟迟不回复消息才用\n    - 如果对方只是短暂不回复，应该使用wait而不是complete_talk"

            if not self.is_remove and self.is_enhance:
                action_list.append(ACTION_WAIT_ENHANCED)

            action_list.append(ACTION_COMPLETE_TALK % complete_note)
            
            action_blocks_text = "\n\n".join(action_list)

            # [核心逻辑] 直接更新 global_prompt_manager 中的 prompt 内容
            
            # 1. 更新 brain_planner_prompt_react
            if "brain_planner_prompt_react" in global_prompt_manager._prompts:
                new_planner_prompt = PLANNER_TEMPLATE.replace("{action_blocks}", action_blocks_text)
                
                # 创建新的 Prompt 对象并覆盖
                # 兼容性处理：检查 Prompt 是否接受 _should_register 参数
                try:
                    new_prompt_obj = Prompt(new_planner_prompt, "brain_planner_prompt_react", _should_register=False)
                except TypeError:
                    new_prompt_obj = Prompt(new_planner_prompt, "brain_planner_prompt_react")
                
                # 强制写入字典
                global_prompt_manager._prompts["brain_planner_prompt_react"] = new_prompt_obj
                self.logger.info("已成功更新 brain_planner_prompt_react")
            
            # 2. 更新 brain_action_prompt
            if "brain_action_prompt" in global_prompt_manager._prompts:
                try:
                    new_action_prompt_obj = Prompt(ACTION_TEMPLATE, "brain_action_prompt", _should_register=False)
                except TypeError:
                    new_action_prompt_obj = Prompt(ACTION_TEMPLATE, "brain_action_prompt")
                    
                global_prompt_manager._prompts["brain_action_prompt"] = new_action_prompt_obj
                self.logger.info("已成功更新 brain_action_prompt")
            
            self.logger.info("Planner prompt 更新完成")
                
        except Exception as e:
            self.logger.error(f"替换 Planner 动作失败: {e}", exc_info=True)

    def get_plugin_components(self):
        return []