"""MQ pattern detector — Kafka, RabbitMQ, RocketMQ, Celery.

Detects message-queue producers and consumers in source code,
creating Route nodes with ``RouteProtocol.MQ``.
"""

from __future__ import annotations

import logging
import os
import re
from typing import List, Optional

from codewiki.src.be.dependency_analyzer.models.cross_service import (
    RouteNode,
    RouteProtocol,
    RouteRole,
)
from codewiki.src.be.dependency_analyzer.utils.path_canonicalizer import make_mq_route_key

logger = logging.getLogger(__name__)


def _get_relative_path(file_path: str) -> str:
    try:
        return os.path.relpath(file_path)
    except (ValueError, TypeError):
        return str(file_path)


def _component_id(file_path: str, func_name: str, class_name: str = "") -> str:
    rel = _get_relative_path(file_path)
    if class_name:
        return f"{rel}::{class_name}.{func_name}"
    return f"{rel}::{func_name}"


# ---- Pattern definitions ----
# Each pattern is (regex, broker, role, group_indices_for_topic_and_func)
# group_indices: (topic_group, ) — func_name is found from enclosing function


class _Pattern:
    def __init__(self, pattern: re.Pattern, broker: str, role: RouteRole, topic_group: int = 1):
        self.pattern = pattern
        self.broker = broker
        self.role = role
        self.topic_group = topic_group


# Kafka
_KAFKA_PRODUCER = _Pattern(
    re.compile(
        r'(?:kafkaTemplate|producer|kafkaProducer)\s*\.\s*(?:send|sendDefault)\s*\(\s*"([^"]+)"',
        re.MULTILINE,
    ),
    broker="kafka",
    role=RouteRole.CLIENT,
    topic_group=1,
)

_KAFKA_CONSUMER = _Pattern(
    re.compile(
        r'@KafkaListener\s*\(\s*(?:topics\s*=\s*)?(?:\{)?\s*"([^"]+)"',
        re.MULTILINE,
    ),
    broker="kafka",
    role=RouteRole.SERVER,
    topic_group=1,
)

# RabbitMQ
_RABBIT_PRODUCER = _Pattern(
    re.compile(
        r'(?:rabbitTemplate|amqpTemplate)\s*\.\s*(?:convertAndSend|send)\s*\(\s*"([^"]+)"',
        re.MULTILINE,
    ),
    broker="rabbitmq",
    role=RouteRole.CLIENT,
    topic_group=1,
)

_RABBIT_CONSUMER = _Pattern(
    re.compile(
        r'@RabbitListener\s*\(\s*(?:queues\s*=\s*)?\s*"([^"]+)"',
        re.MULTILINE,
    ),
    broker="rabbitmq",
    role=RouteRole.SERVER,
    topic_group=1,
)

# RocketMQ
_ROCKET_PRODUCER = _Pattern(
    re.compile(
        r'(?:rocketMQTemplate|defaultMQProducer)\s*\.\s*(?:send|convertAndSend|syncSend)\s*\(\s*"([^"]+)"',
        re.MULTILINE,
    ),
    broker="rocketmq",
    role=RouteRole.CLIENT,
    topic_group=1,
)

_ROCKET_CONSUMER = _Pattern(
    re.compile(
        r'@RocketMQMessageListener\s*\([^)]*topic\s*=\s*"([^"]+)"',
        re.MULTILINE,
    ),
    broker="rocketmq",
    role=RouteRole.SERVER,
    topic_group=1,
)

# Celery
_CELERY_PRODUCER = _Pattern(
    re.compile(
        r'(?:celery|app)\s*\.\s*send_task\s*\(\s*"([^"]+)"',
        re.MULTILINE,
    ),
    broker="celery",
    role=RouteRole.CLIENT,
    topic_group=1,
)

_CELERY_CONSUMER = _Pattern(
    re.compile(
        r'@(?:celery|app)\s*\.\s*task\s*(?:\(\s*name\s*=\s*"([^"]+)")?',
        re.MULTILINE,
    ),
    broker="celery",
    role=RouteRole.SERVER,
    topic_group=1,
)

# Python Kafka (kafka-python / confluent-kafka)
_PY_KAFKA_PRODUCER = _Pattern(
    re.compile(
        r'(?:producer|kafka_producer)\s*\.\s*(?:send|produce)\s*\(\s*["\']([^"\']+)["\']',
        re.MULTILINE,
    ),
    broker="kafka",
    role=RouteRole.CLIENT,
    topic_group=1,
)

# Go Kafka (segmentio/kafka-go, confluent-kafka-go)
_GO_KAFKA_PRODUCER = _Pattern(
    re.compile(
        r'(?:writer|producer)\s*\.\s*(?:WriteMessages|Produce)\s*\([^,]*,\s*kafka\.Message\{[^}]*Topic:\s*"([^"]+)"',
        re.MULTILINE | re.DOTALL,
    ),
    broker="kafka",
    role=RouteRole.CLIENT,
    topic_group=1,
)

ALL_PATTERNS = [
    _KAFKA_PRODUCER,
    _KAFKA_CONSUMER,
    _RABBIT_PRODUCER,
    _RABBIT_CONSUMER,
    _ROCKET_PRODUCER,
    _ROCKET_CONSUMER,
    _CELERY_PRODUCER,
    _CELERY_CONSUMER,
    _PY_KAFKA_PRODUCER,
    _GO_KAFKA_PRODUCER,
]


def extract_mq_routes(file_path: str, content: str, repo_name: str) -> List[RouteNode]:
    """Extract MQ producer/consumer routes from any language source file."""
    routes: List[RouteNode] = []
    _get_relative_path(file_path)

    for pat in ALL_PATTERNS:
        for m in pat.pattern.finditer(content):
            topic = (
                m.group(pat.topic_group)
                if pat.topic_group <= len(m.groups()) and m.group(pat.topic_group)
                else ""
            )
            if not topic:
                # For Celery @app.task without name, use function name
                func_name = _find_enclosing_function(content, m.start())
                if func_name:
                    topic = func_name
                else:
                    continue

            lineno = content[: m.start()].count("\n") + 1
            func_name = _find_enclosing_function(content, m.start()) or "unknown"

            # Determine class name for Java/Kotlin
            class_name = _find_enclosing_class(content, m.start())

            routes.append(
                RouteNode(
                    route_key=make_mq_route_key(pat.broker, topic),
                    protocol=RouteProtocol.MQ,
                    method=None,
                    path=topic,
                    role=pat.role,
                    component_id=_component_id(file_path, func_name, class_name),
                    repo_name=repo_name,
                    file_path=file_path,
                    line_number=lineno,
                    framework=pat.broker,
                    extra={"broker": pat.broker, "topic": topic},
                )
            )

    return routes


def _find_enclosing_function(content: str, pos: int) -> Optional[str]:
    """Find enclosing function/method name — works across languages."""
    before = content[:pos]
    # Java/Kotlin/C#/Go: func/method declarations
    patterns = [
        # Java/Kotlin: (public|private|...) Type methodName(
        re.compile(
            r"(?:public|private|protected|static|final|synchronized|abstract|\s)+\s+\S+\s+(\w+)\s*\("
        ),
        # Python: def func_name(
        re.compile(r"def\s+(\w+)\s*\("),
        # Go: func (receiver)? name(
        re.compile(r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\("),
        # JS/TS: function name( or const name = ( or name(
        re.compile(r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=|async\s+(\w+)\s*\()"),
    ]
    for pat in patterns:
        matches = list(pat.finditer(before))
        if matches:
            last = matches[-1]
            for g in range(1, last.lastindex + 1 if last.lastindex else 2):
                val = last.group(g)
                if val:
                    return val
    return None


def _find_enclosing_class(content: str, pos: int) -> str:
    before = content[:pos]
    matches = list(re.finditer(r"(?:class|interface)\s+(\w+)", before))
    return matches[-1].group(1) if matches else ""
