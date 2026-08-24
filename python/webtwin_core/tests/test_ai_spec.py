"""AI spec export tests."""

from uuid import uuid4

from webtwin_core.models import (
    BusinessRule,
    ElementSnapshot,
    Investigation,
    InvestigationStatus,
    Observation,
    RuleCondition,
    RuleEffect,
    RuleStatus,
    TimelineEvent,
    TimelineEventType,
)
from webtwin_core.models.spa import RouteSnapshot
from webtwin_core.models.workflow import Workflow, WorkflowStep
from webtwin_core.reference_system import ScreenField, build_reference_system_context
from webtwin_core.reference_system.ai_spec import (
    build_ai_spec,
    classify_route_path,
    filter_interaction_fields,
    is_export_noise,
    is_interaction_field,
)
from webtwin_core.reference_system.site_graph import DiscoveredLink, LinkType


def test_is_interaction_field_excludes_bare_anchors() -> None:
    assert is_interaction_field(ScreenField(name="a", selector="a")) is False
    assert is_interaction_field(
        ScreenField(name='a[href="/about"]', selector='a[href="/about"]')
    ) is False
    assert is_interaction_field(
        ScreenField(name="email", selector="#email", input_type="email", label="Email")
    ) is True


def test_is_export_noise_filters_tracking_and_nonces() -> None:
    assert is_export_noise(ScreenField(name="wc_order_attribution_user_agent", input_type="hidden"))
    assert is_export_noise(ScreenField(name="woocommerce-login-nonce", input_type="hidden"))
    assert is_export_noise(ScreenField(name="variation_id", input_type="hidden"))
    assert not is_export_noise(
        ScreenField(name="quantity", input_type="number", label="Product quantity")
    )


def test_classify_route_path() -> None:
    assert classify_route_path("/") == "static"
    assert classify_route_path("/forms/hearing/abc") == "form"
    assert classify_route_path("/product-category/men/") == "category"
    assert classify_route_path("/product/shirt/") == "product"
    assert classify_route_path("/cart-2/") == "cart"
    assert classify_route_path("/wp-login.php") == "auth"


def test_build_ai_spec_filters_navigation_noise() -> None:
    inv_id = uuid4()
    investigation = Investigation(
        id=inv_id,
        goal="test",
        target_url="https://example.com/",
        status=InvestigationStatus.COMPLETED,
    )
    observation = Observation(
        investigation_id=inv_id,
        url="https://example.com/",
        title="Home",
        route=RouteSnapshot(url="https://example.com/", path="/", title="Home"),
        elements=[
            ElementSnapshot(selector="a", tag="a", name="a", stable_key="a"),
            ElementSnapshot(
                selector='a[href="/about"]',
                tag="a",
                name='a[href="/about"]',
                stable_key='a[href="/about"]',
            ),
            ElementSnapshot(
                selector="#search",
                tag="input",
                name="search",
                stable_key="search",
                input_type="search",
                label="Search",
            ),
        ],
    )
    verified = BusinessRule(
        investigation_id=inv_id,
        name="search visible on home",
        condition=RuleCondition(field="page", operator="equals", value="/"),
        effect=RuleEffect(field="search", visible=True),
        status=RuleStatus.VERIFIED,
        confidence=0.9,
    )
    reference = build_reference_system_context(
        investigation,
        observations=[observation],
        events=[],
        rules=[verified],
        discovered_links=[
            DiscoveredLink(
                investigation_id=inv_id,
                from_screen_id="/",
                to_screen_id="/about",
                href="https://example.com/about",
                visited=True,
                link_type=LinkType.NAVIGATE,
            ),
        ],
    )
    spec = build_ai_spec(investigation, reference, [verified])
    assert spec.summary.screen_count == 1
    assert spec.summary.verified_rule_count == 1
    assert len(spec.navigation) == 1
    assert "Verified behavior" in spec.markdown
    assert "a[href" not in spec.markdown
    assert spec.route_groups[0].kind == "static"


def test_build_ai_spec_deduplicates_layout_and_strips_noise() -> None:
    inv_id = uuid4()
    investigation = Investigation(
        id=inv_id,
        goal="catalog",
        target_url="https://shop.example/",
        status=InvestigationStatus.COMPLETED,
    )

    def page_obs(path: str, title: str, extra: list[ElementSnapshot] | None = None) -> Observation:
        elements = [
            ElementSnapshot(
                selector="#menu",
                tag="button",
                name="main_menu_toggle",
                stable_key="main_menu_toggle",
                label="Main menu toggle",
            ),
            ElementSnapshot(
                selector="#s",
                tag="input",
                name="s",
                stable_key="s",
                input_type="search",
                label="Search for:",
            ),
            *(extra or []),
        ]
        return Observation(
            investigation_id=inv_id,
            url=f"https://shop.example{path}",
            title=title,
            route=RouteSnapshot(url=f"https://shop.example{path}", path=path, title=title),
            elements=elements,
        )

    observations = [
        page_obs("/", "Home"),
        page_obs("/about/", "About"),
        page_obs("/cart-2/", "Cart"),
        page_obs(
            "/my-account-2/",
            "Account",
            [
                ElementSnapshot(
                    selector="#email",
                    tag="input",
                    name="email",
                    stable_key="email",
                    input_type="email",
                    label="Email",
                    required=True,
                ),
                ElementSnapshot(
                    selector="#wc",
                    tag="input",
                    name="wc_order_attribution_user_agent",
                    stable_key="wc_order_attribution_user_agent",
                    input_type="hidden",
                ),
                ElementSnapshot(
                    selector="#nonce",
                    tag="input",
                    name="woocommerce-login-nonce",
                    stable_key="woocommerce-login-nonce",
                    input_type="hidden",
                ),
            ],
        ),
        page_obs(
            "/product/shirt/",
            "Shirt",
            [
                ElementSnapshot(
                    selector="#qty",
                    tag="input",
                    name="quantity",
                    stable_key="quantity",
                    input_type="number",
                    label="Product quantity",
                ),
                ElementSnapshot(
                    selector="#vid",
                    tag="input",
                    name="variation_id",
                    stable_key="variation_id",
                    input_type="hidden",
                ),
            ],
        ),
    ]

    reference = build_reference_system_context(
        investigation,
        observations=observations,
        events=[],
        rules=[],
    )
    spec = build_ai_spec(investigation, reference, [])

    layout_names = {field.name for field in spec.layout}
    assert "main_menu_toggle" in layout_names
    assert "s" in layout_names
    assert "Global layout (shared chrome)" in spec.markdown
    assert "wc_order_attribution_user_agent" not in spec.markdown
    assert "woocommerce-login-nonce" not in spec.markdown
    assert "variation_id" not in spec.markdown

    account = next(item for item in spec.interactions if item.path == "/my-account-2/")
    assert any(field.name == "email" for field in account.fields)
    assert all(field.name not in layout_names for field in account.fields)

    product = next(item for item in spec.interactions if item.path == "/product/shirt/")
    assert any(field.name == "quantity" for field in product.fields)

    kinds = {group.kind for group in spec.route_groups}
    assert {"static", "cart", "auth", "product"}.issubset(kinds)
    assert spec.summary.layout_field_count == 2
    assert spec.summary.interaction_field_count < spec.summary.unique_interaction_field_count + 10


def test_build_ai_spec_normalizes_flow_steps() -> None:
    inv_id = uuid4()
    investigation = Investigation(
        id=inv_id,
        goal="flow",
        target_url="https://example.com/",
        status=InvestigationStatus.COMPLETED,
    )
    observation = Observation(
        investigation_id=inv_id,
        url="https://example.com/",
        title="Home",
        route=RouteSnapshot(url="https://example.com/", path="/", title="Home"),
        elements=[
            ElementSnapshot(
                selector="#search",
                tag="input",
                name="search",
                stable_key="search",
                input_type="search",
                label="Search",
            ),
        ],
    )
    workflow = Workflow(
        investigation_id=inv_id,
        name="Browse flow",
        steps=[
            WorkflowStep(order=0, description="Opened https://example.com/"),
            WorkflowStep(
                order=1,
                description='a[href="https://example.com/about/"]=https://example.com/about/ (nav)',
            ),
        ],
    )
    reference = build_reference_system_context(
        investigation,
        observations=[observation],
        events=[
            TimelineEvent(
                investigation_id=inv_id,
                type=TimelineEventType.NAVIGATE,
                description="nav",
            )
        ],
        rules=[],
        workflows=[workflow],
    )
    spec = build_ai_spec(investigation, reference, [])
    assert spec.flows
    assert "Open `/`" in spec.flows[0].steps[0]
    assert "Navigate to `/about/`" in spec.flows[0].steps[1]


def test_collapse_interactions_groups_identical_edit_screens() -> None:
    from webtwin_core.reference_system.ai_spec import (
        AiInteractionField,
        AiScreenInteractions,
        _collapse_interactions,
    )

    fields = [
        AiInteractionField(name="first_name", label="名", input_type="text", entity="JobSeeker"),
        AiInteractionField(name="email", label="Email", input_type="email", entity="Contact"),
    ]
    interactions = [
        AiScreenInteractions(
            screen_id=f"/job-seeker-management/edit/{item}",
            path=f"/job-seeker-management/edit/{item}",
            name="JobSeeker edit",
            kind="static",
            fields=fields,
        )
        for item in (458, 459, 460)
    ]
    collapsed = _collapse_interactions(interactions)
    assert len(collapsed) == 1
    assert collapsed[0].pattern == "/job-seeker-management/edit/:id"
    assert collapsed[0].instance_count == 3
    assert "/job-seeker-management/edit/458" in collapsed[0].examples
