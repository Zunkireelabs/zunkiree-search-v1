# Zunkiree Widget — End-User Flow Architecture

> Mermaid diagrams mapping the complete user journey through the Zunkiree shopping widget.
> Open in GitHub or VS Code Mermaid preview to render.

---

## 1. Widget Lifecycle — State Machine

Three top-level visual modes the widget can be in at any time.

```mermaid
stateDiagram-v2
    [*] --> bottom_minimized : Page load

    bottom_minimized --> bottom_expanded : Click FAB / CollapsedBar
    bottom_minimized --> bottom_expanded : Send message (auto-expand)

    bottom_expanded --> bottom_minimized : Click minimize button
    bottom_expanded --> bottom_minimized : Click backdrop
    bottom_expanded --> right_docked : Click dock button (viewport >= 1024px)

    right_docked --> bottom_expanded : Click undock button
    right_docked --> bottom_minimized : Click minimize button
    right_docked --> bottom_expanded : Viewport resized below 1024px (exitDock callback)
```

---

## 2. Session & Config Initialization

What happens from the moment the host page loads the widget script.

```mermaid
sequenceDiagram
    participant Page as Host Page
    participant Main as main.tsx
    participant Widget as Widget.tsx
    participant LS as localStorage
    participant API as Backend API

    Page->>Main: <script data-site-id data-api-url data-mode>
    Main->>Main: Read data attributes from script tag
    Main->>Main: Create #zunkiree-widget-root div on body
    Main->>Widget: ReactDOM.createRoot → render <Widget>

    Widget->>LS: Read `zk-session-{siteId}`
    alt Session exists
        LS-->>Widget: Restore sessionId
    else No session
        Widget->>Widget: crypto.randomUUID()
        Widget->>LS: Store new sessionId
    end

    Widget->>Widget: bootstrap() — create layout wrapper (useLayoutEffect)
    Widget->>Widget: setDockPortalTarget(getDockPanel())

    Widget->>API: GET /v1/sites/{siteId}/config
    alt Success
        API-->>Widget: WidgetConfig (brand_name, primary_color, etc.)
    else Failure
        Widget->>Widget: Use fallback config
    end

    Widget->>Widget: Render CollapsedBar (bottom-minimized)
```

---

## 3. Chat & SSE Flow

Two parallel paths depending on `widgetMode`: **search** vs **agent**.

```mermaid
flowchart TB
    subgraph UserAction["User Sends Message"]
        A[Type message + press Enter] --> B{widgetMode?}
    end

    subgraph SearchMode["Search Mode — /api/v1/query/stream"]
        B -- search --> S1[POST payload: site_id, question, session_id, language]
        S1 --> S2[Open SSE reader]
        S2 --> S3{Parse SSE line}
        S3 -- "type: token" --> S4[Append text to streaming content]
        S3 -- "type: products" --> S5[Attach product array to message]
        S3 -- "type: cart_update" --> S6[Attach cart state to message]
        S3 -- "type: checkout" --> S7[Attach checkout data to message]
        S3 -- "type: tool_call" --> S8[Show tool status indicator]
        S3 -- "type: done" --> S9[Finalize answer + suggestions + persist session_id]
        S3 -- "type: error" --> S10[Show error message]
        S4 --> S3
        S5 --> S3
        S6 --> S3
        S7 --> S3
        S8 --> S3
    end

    subgraph AgentMode["Agent Mode — /v1/sites/{siteId}/agent/chat"]
        B -- agent --> A1[POST payload: sessionId, message + X-Session-Id header]
        A1 --> A2[Open SSE reader]
        A2 --> A3{Parse SSE event type}
        A3 -- "event: message" --> A4[Append text content]
        A3 -- "event: tool_call" --> A5[Show tool running status]
        A3 -- "event: tool_result" --> A6[Clear tool status]
        A3 -- "event: render" --> A7["Dispatch render event (product_grid, product_detail, cart_view, checkout, etc.)"]
        A3 -- "event: done" --> A8[Finalize message, clear loading]
        A3 -- "event: error" --> A9[Show error message]
        A4 --> A3
        A5 --> A3
        A6 --> A3
        A7 --> A3
    end
```

---

## 4. Full Shopping Journey — Flowchart

The main end-to-end user flow through the ecommerce experience.

```mermaid
flowchart TD
    Start([User opens widget]) --> Browse[Browse / Ask question]
    Browse --> ProductGrid["Product Grid\n(AgentProductGrid)"]
    ProductGrid --> ViewDetails[Click 'View Details']
    ViewDetails --> ProductDetail["Product Detail\n(AgentProductDetail)"]

    ProductDetail --> SelectVariation{Has variations?}
    SelectVariation -- Yes --> PickSize[Select size/color]
    SelectVariation -- No --> SetQty[Set quantity]
    PickSize --> SetQty

    SetQty --> AddToCart[Click 'Add to Cart']
    AddToCart --> AgentProcesses[Agent processes add-to-cart message]
    AgentProcesses --> CartView["Cart View\n(AgentCartView)"]

    ProductDetail --> Wishlist[Click wishlist heart icon]
    Wishlist --> WishlistView["Wishlist View\n(WishlistView)"]
    WishlistView --> MoveToCart[Add to Cart from wishlist]
    MoveToCart --> AgentProcesses

    CartView --> RemoveItem[Remove item]
    RemoveItem --> AgentProcesses

    CartView --> Checkout["Click 'Proceed to Checkout'"]
    Checkout --> AgentCheckout["Checkout Flow\n(AgentCheckout)"]

    AgentCheckout --> Shipping["Step 1: Shipping Form\n(ShippingForm)"]
    Shipping --> CreateOrder[POST /v1/sites/.../orders]
    CreateOrder --> Payment["Step 2: Payment Selection\n(PaymentSelector)"]

    Payment --> SelectGateway{Select gateway}
    SelectGateway -- eSewa --> OpenPopup["Open popup window\nPOST /v1/sites/.../payments/initiate"]
    SelectGateway -- Khalti --> OpenPopup

    OpenPopup --> AwaitPayment["Step 2.5: Awaiting Payment\nPolling /payments/{id}/status every 3s"]

    AwaitPayment --> PaymentResult{Payment status?}
    PaymentResult -- completed --> Confirmation["Step 3: Order Confirmed!\n(OrderConfirmation)"]
    PaymentResult -- failed --> Failed["Payment Failed screen"]
    PaymentResult -- popup closed --> FinalCheck[Final status check]
    FinalCheck -- completed --> Confirmation
    FinalCheck -- not completed --> Failed
    PaymentResult -- "timeout (10 min)" --> Failed

    Failed --> RetryPayment[Click 'Try Again']
    RetryPayment --> Payment

    AwaitPayment --> CancelPayment[Click 'Cancel']
    CancelPayment --> Payment

    Confirmation --> ContinueShopping[Click 'Continue Shopping']
    ContinueShopping --> Browse

    ProductGrid --> BackToBrowse[Ask another question]
    BackToBrowse --> Browse
```

---

## 5. Checkout & Payment — Detailed State Machine

The `AgentCheckout` component's internal step transitions.

```mermaid
stateDiagram-v2
    [*] --> shipping : Component mounts

    shipping --> payment : ShippingForm submitted successfully\nPOST /orders → orderId saved
    shipping --> shipping : Validation error / API error (show error, stay)

    payment --> awaiting_payment : Gateway selected\nPopup opened + POST /payments/initiate\nPolling starts (3s interval)
    payment --> payment : Popup blocked (show error, stay)

    awaiting_payment --> confirmation : Poll returns status=completed\nPopup auto-closed
    awaiting_payment --> failed : Poll returns status=failed\nPopup auto-closed
    awaiting_payment --> failed : Popup closed by user → final check → not completed
    awaiting_payment --> confirmation : Popup closed by user → final check → completed
    awaiting_payment --> failed : 10-minute timeout\nPopup auto-closed
    awaiting_payment --> payment : User clicks 'Cancel'\nPolling stopped, popup closed

    failed --> payment : User clicks 'Try Again'

    confirmation --> [*] : User clicks 'Continue Shopping'\nor stays on confirmation
```

### Payment Popup & Polling Detail

```mermaid
sequenceDiagram
    participant User
    participant Widget as AgentCheckout
    participant Popup as Browser Popup
    participant API as Backend API
    participant Gateway as eSewa / Khalti

    User->>Widget: Select payment gateway
    Widget->>Popup: window.open('about:blank')
    Widget->>API: POST /v1/sites/{siteId}/payments/initiate
    API-->>Widget: paymentId + paymentUrl (+ formData for eSewa)

    alt eSewa
        Widget->>Popup: Write HTML form + auto-submit
        Popup->>Gateway: POST form to eSewa
    else Khalti
        Widget->>Popup: popup.location.href = paymentUrl
        Popup->>Gateway: Navigate to Khalti
    end

    Widget->>Widget: setStep('awaiting_payment')

    loop Every 3 seconds (max 10 min)
        Widget->>API: GET /v1/sites/{siteId}/payments/{paymentId}/status
        alt completed
            API-->>Widget: status: completed
            Widget->>Popup: Close popup
            Widget->>Widget: setStep('confirmation')
        else failed
            API-->>Widget: status: failed
            Widget->>Popup: Close popup
            Widget->>Widget: setStep('failed')
        else pending
            API-->>Widget: status: pending
            Note over Widget: Continue polling
        end
    end

    Note over Widget: If popup.closed detected → one final status check
    Note over Widget: If 10-min timeout → stop polling, close popup, set 'failed'
```

---

## 6. Cart Badge Lifecycle

How the header cart icon and badge count stay in sync.

```mermaid
flowchart LR
    A["SSE render event:\ncomponent = 'cart_view'"] --> B["Widget.tsx:\nsetCartItemCount(re.props.items.length)"]
    B --> C["cartItemCount passed as\nprop to ExpandedPanel / DockedPanel"]
    C --> D{"cartItemCount > 0\nAND enableShopping?"}
    D -- Yes --> E["Show cart icon + badge\nin panel header"]
    D -- No --> F["Hide cart icon"]
    E --> G["User clicks cart icon"]
    G --> H["handleViewCart()\nsends 'Show my cart' message"]
    H --> I["Agent returns cart_view render event"]
    I --> A
```

---

## 7. Ecommerce Gating

How `enable_shopping` controls which components render.

```mermaid
flowchart TD
    Config["GET /v1/sites/{siteId}/config"] --> Check{"config.enable_shopping\n=== true?"}

    Check -- Yes --> EnabledPath["enableShopping = true"]
    Check -- "No / undefined" --> DisabledPath["enableShopping = false"]

    EnabledPath --> RenderAll["Render all components:\nproduct_grid\nproduct_detail\ncart_view\nwishlist_view\ncheckout\norder_confirmation\ncategories"]

    DisabledPath --> GateCheck{"Is component in ecommerce list?"}
    GateCheck -- Yes --> Skip["return null (skip render)"]
    GateCheck -- No --> RenderSafe["Render non-ecommerce components:\ncategories, text messages, etc."]

    subgraph EcommerceGate["Ecommerce Component Gate"]
        direction LR
        G1[product_grid]
        G2[product_detail]
        G3[cart_view]
        G4[wishlist_view]
        G5[checkout]
        G6[order_confirmation]
    end
```

---

## Source File Reference

| File | Responsibility |
|------|---------------|
| `src/main.tsx` | Script tag bootstrap, DOM root creation |
| `src/components/Widget.tsx` | Top-level state, mode transitions, SSE handlers |
| `src/components/ExpandedPanel.tsx` | Floating panel with render event dispatch |
| `src/components/DockedPanel.tsx` | Side-docked panel (mirrors ExpandedPanel) |
| `src/components/agent/AgentCheckout.tsx` | Checkout state machine, payment popup + polling |
| `src/components/agent/AgentProductGrid.tsx` | Horizontal scrollable product cards |
| `src/components/agent/AgentProductDetail.tsx` | Product detail with variations + quantity |
| `src/components/agent/AgentCartView.tsx` | Cart item list + checkout CTA |
| `src/components/agent/OrderConfirmation.tsx` | Post-payment confirmation screen |
| `src/components/agent/PaymentSelector.tsx` | eSewa / Khalti gateway selection |
