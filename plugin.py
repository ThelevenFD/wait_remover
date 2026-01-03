from src.plugin_system import register_plugin
from src.chat.utils.prompt_builder import Prompt
from src.plugin_system import BasePlugin, ConfigField
from src.common.logger import get_logger
from src.chat.utils.prompt_builder import global_prompt_manager
import asyncio
import re

wait_action_text = """
wait
动作描述：
暂时不再发言，等待指定时间。适用于以下情况：
- 你已经表达清楚一轮，想给对方留出空间
- 你感觉对方的话还没说完，或者自己刚刚发了好几条连续消息
- 你想要等待一定时间来让对方把话说完，或者等待对方反应
- 你想保持安静，专注"听"而不是马上回复
请你根据上下文来判断要等待多久，请你灵活判断：
- 如果你们交流间隔时间很短，聊的很频繁，不宜等待太久
- 如果你们交流间隔时间很长，聊的很少，可以等待较长时间
{{
    "action": "wait",
    "target_message_id":"想要作为这次等待依据的消息id（通常是对方的最新消息）",
    "reason":"选择等待的原因"
}}"""

complete_replace_text = """
- 多次wait之后，对方迟迟不回复消息才用
- 如果对方只是短暂不回复，应该使用wait而不是complete_talk"""

brain_planner_prompt_react = """
{time_block}
{name_block}
{chat_context_description}，以下是具体的聊天内容

**聊天内容**
{chat_content_block}

**动作记录**
{actions_before_now_block}

**可用的action**
reply
动作描述：
进行回复，你可以自然的顺着正在进行的聊天内容进行回复或自然的提出一个问题
{{
    "action": "reply",
    "target_message_id":"想要回复的消息id",
    "reason":"回复的原因"
}}

wait
动作描述：
暂时不再发言，等待指定时间。适用于以下情况：
- 你已经表达清楚一轮，想给对方留出空间
- 你感觉对方的话还没说完，或者自己刚刚发了好几条连续消息
- 你想要等待一定时间来让对方把话说完，或者等待对方反应
- 你想保持安静，专注"听"而不是马上回复
请你根据上下文来判断要等待多久，请你灵活判断：
- 如果你们交流间隔时间很短，聊的很频繁，不宜等待太久
- 如果你们交流间隔时间很长，聊的很少，可以等待较长时间
{{
    "action": "wait",
    "target_message_id":"想要作为这次等待依据的消息id（通常是对方的最新消息）",
    "reason":"选择等待的原因"
}}

complete_talk
动作描述：
当前聊天暂时结束了，对方离开，没有更多话题了
你可以使用该动作来暂时休息，等待对方有新发言再继续：
- 多次wait之后，对方迟迟不回复消息才用
- 如果对方只是短暂不回复，应该使用wait而不是complete_talk
- 聊天内容显示当前聊天已经结束或者没有新内容时候，选择complete_talk
选择此动作后，将不再继续循环思考，直到收到对方的新消息
{{
    "action": "complete_talk",
    "target_message_id":"触发完成对话的消息id（通常是对方的最新消息）",
    "reason":"选择完成对话的原因"
}}

{action_options_text}

请选择合适的action，并说明触发action的消息id和选择该action的原因。消息id格式:m+数字
先输出你的选择思考理由，再输出你选择的action，理由是一段平文本，不要分点，精简。
**动作选择要求**
请你根据聊天内容,用户的最新消息和以下标准选择合适的动作:
{plan_style}
{moderation_prompt}

请选择所有符合使用要求的action，动作用json格式输出，如果输出多个json，每个json都要单独用```json包裹，你可以重复使用同一个动作或不同动作:
**示例**
// 理由文本
```json
{{
    "action":"动作名",
    "target_message_id":"触发动作的消息id",
    //对应参数
}}
```
```json
{{
    "action":"动作名",
    "target_message_id":"触发动作的消息id",
    //对应参数
}}
```

"""

brain_action_prompt = """
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

def init_prompt_():
    # ReAct 形式的 Planner Prompt
    Prompt(brain_planner_prompt_react, "brain_planner_prompt_react")
    Prompt(brain_action_prompt, "brain_action_prompt")

WAIT_PATTERN = r'wait\s*动作描述：.*?"action": "wait",\s*"target_message_id":.*?"reason":"选择等待的原因"\s*}}'

@register_plugin
class Plugin(BasePlugin):
    plugin_name = "wait_remover"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"
    config_schema = {
        "plugin": {
            "config_version": ConfigField(type=str, default="1.0.2", description="配置版本"),
            "change_wait_action": ConfigField(type=bool, default=True, description="改善wait动作(推荐)"),
            "remove_wait_action": ConfigField(type=bool, default=False, description="移除私聊的wait动作"),
        }
    }
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = get_logger(self.plugin_name)
        self._setup_actions()
    
    def _setup_actions(self):
        """根据配置设置相应的动作"""
        if self.get_config("plugin.remove_wait_action"):
            self.logger.info("启用移除wait动作")
            asyncio.create_task(self._modify_prompt(""))
        elif self.get_config("plugin.change_wait_action"):
            self.logger.info("启用改善wait动作")
            asyncio.create_task(self._modify_prompt(wait_action_text))
        else:
            self.logger.error("未启用任何功能")
    
    async def _modify_prompt(self, new_wait_text):
        """修改prompt模板中的wait动作"""
        await asyncio.sleep(5)
        
        try:
            prompt_template = await global_prompt_manager.get_prompt_async(name="brain_planner_prompt_react")
            new_prompt = re.sub(WAIT_PATTERN, new_wait_text, prompt_template, flags=re.DOTALL)
            global_prompt_manager.add_prompt(name="brain_planner_prompt_react", fstr=new_prompt)
            
            action = "移除" if not new_wait_text else "修改"
            self.logger.info(f"成功{action}wait动作")
            
        except Exception as e:
            self.logger.error(f"{action}wait动作失败: {e}")
    
    def get_plugin_components(self):
        return []