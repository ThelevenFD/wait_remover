from src.plugin_system import register_plugin
from src.chat.utils.prompt_builder import Prompt
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.config_types import ConfigField
from src.common.logger import get_logger
import asyncio

def init_prompt_():
    # ReAct 形式的 Planner Prompt
    Prompt(
        """
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

complete_talk
动作描述：
当前聊天暂时结束了，对方离开，没有更多话题了
你可以使用该动作来暂时休息，等待对方有新发言再继续：
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

""",
        "brain_planner_prompt_react",
    )

    Prompt(
        """
{action_name}
动作描述：{action_description}
使用条件：
{action_require}
{{
    "action": "{action_name}",{action_parameters},
    "target_message_id":"触发action的消息id",
    "reason":"触发action的原因"
}}
""",
        "brain_action_prompt",
    )

@register_plugin
class Plugin(BasePlugin):
    plugin_name = "wait_remover"
    enable_plugin = True
    dependencies = []
    python_dependencies = []
    config_file_name = "config.toml"
    config_schema: dict = {
        "plugin": {
            "config_version": ConfigField(type=str, default="1.0.1", description="配置版本(不要修改 除非你知道自己在干什么)"),
            "remove_wait_action": ConfigField(type=bool, default=True, description="移除私聊的wait动作"),
    }
}
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        global logger
        logger = get_logger(self.plugin_name)
        if self.get_config("plugin.remove_wait_action"):
            asyncio.create_task(self.remove_action())
        else:
            logger.info("未启用移除wait动作")

    def get_plugin_components(self):
        return []
    


    async def remove_action(self):
        await asyncio.sleep(5)
        import src.chat.brain_chat.brain_planner
        logger.info("尝试移除wait动作")
        try:
            src.chat.brain_chat.brain_planner.init_prompt = init_prompt_()
            if src.chat.brain_chat.brain_planner.init_prompt is init_prompt_():
                logger.info("移除wait动作成功")
        except Exception as e:
            logger.error(f"移除wait动作失败: {e}")
        
