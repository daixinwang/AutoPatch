# agent 包初始化
# 导出编译好的 Graph 应用实例，供 CLI 和 FastAPI 服务复用
def __getattr__(name):
    if name in __all__:
        from agent import graph
        return getattr(graph, name)
    raise AttributeError(name)

__all__ = ["app", "AgentState", "build_graph"]
