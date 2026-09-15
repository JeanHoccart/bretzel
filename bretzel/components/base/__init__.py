"""Component authoring primitives — public API of the base layer.

Component authors import from here ::

    from bretzel.components.base import Component, reactive_prop, el

Anything not re-exported is internal to the framework.
"""

from __future__ import annotations

from bretzel.components.base.attrs import (
    ComponentDefinitionError,
    ComponentUsageError,
    normalize_attr_name,
    split_kwargs,
)
from bretzel.components.base.component import (
    Component,
    coerce_children,
    el,
    reject_component,
    stamp_display_none,
)
from bretzel.components.base.events import (
    HandlerError,
    action_attrs,
    client_event_attr,
    encode_handler_id,
    item_action_attrs,
)
from bretzel.components.base.reactive_prop import (
    MISSING,
    ReactivePropDescriptor,
    looks_like_client_expr,
    reactive_prop,
    reads_as_client_expr,
)
from bretzel.components.base.responsive import (
    BASE_KEYS,
    BREAKPOINTS,
    reject_stray_breakpoints,
    responsive_classes,
)
from bretzel.components.base.sizes import (
    SIZE_SCALE,
    is_size_keyed,
    size_vocabulary,
)

__all__ = [
    # Author surface
    "Component",
    "reactive_prop",
    "el",
    "MISSING",
    # Helpers exposed for sub-component composition / advanced authors
    "ReactivePropDescriptor",
    "looks_like_client_expr",
    "reads_as_client_expr",
    "split_kwargs",
    "normalize_attr_name",
    "action_attrs",
    "client_event_attr",
    "item_action_attrs",
    "encode_handler_id",
    "stamp_display_none",
    "coerce_children",
    # Responsive ({breakpoint: value}) prop values
    "responsive_classes",
    "SIZE_SCALE",
    "is_size_keyed",
    "size_vocabulary",
    "reject_stray_breakpoints",
    "reject_component",
    "BASE_KEYS",
    "BREAKPOINTS",
    # Errors
    "ComponentDefinitionError",
    "ComponentUsageError",
    "HandlerError",
]
