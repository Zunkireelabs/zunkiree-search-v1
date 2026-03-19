export const agentStyles = (primaryColor: string) => `
  /* ===== Agent Product Grid ===== */
  .zk-agent-grid { margin: 12px 0; }
  .zk-agent-grid__header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 10px; font-size: 12px; color: #6b7280;
  }
  .zk-agent-grid__arrows { display: flex; gap: 4px; }
  .zk-agent-grid__arrow {
    width: 28px; height: 28px; border: 1px solid #e5e7eb; border-radius: 8px;
    background: white; cursor: pointer; display: flex; align-items: center; justify-content: center;
    color: #374151; transition: all 150ms ease;
  }
  .zk-agent-grid__arrow:hover { background: #f9fafb; border-color: #d1d5db; }
  .zk-agent-grid__scroll {
    display: flex; gap: 10px; overflow-x: auto; scroll-snap-type: x mandatory;
    -webkit-overflow-scrolling: touch; padding-bottom: 4px;
    scrollbar-width: thin; scrollbar-color: #e5e7eb transparent;
  }
  .zk-agent-grid__scroll::-webkit-scrollbar { height: 4px; }
  .zk-agent-grid__scroll::-webkit-scrollbar-track { background: transparent; }
  .zk-agent-grid__scroll::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 4px; }

  /* Agent Card */
  .zk-agent-card {
    flex: 0 0 200px; scroll-snap-align: start;
    border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; background: white;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    transition: transform 200ms ease, box-shadow 200ms ease;
  }
  .zk-agent-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  }
  .zk-agent-card__image {
    width: 100%; height: 180px; overflow: hidden; cursor: pointer; background: #f9fafb;
  }
  .zk-agent-card__image img {
    width: 100%; height: 100%; object-fit: cover;
    border-radius: 12px 12px 0 0;
    transition: transform 300ms ease;
  }
  .zk-agent-card__image:hover img { transform: scale(1.05); }
  .zk-agent-card__no-image {
    width: 100%; height: 100%; display: flex; align-items: center; justify-content: center;
  }
  .zk-agent-card__info { padding: 14px; }
  .zk-agent-card__name {
    font-size: 14px; font-weight: 600; color: #111827; cursor: pointer;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    transition: color 150ms ease;
  }
  .zk-agent-card__name:hover { color: ${primaryColor}; }
  .zk-agent-card__price { font-size: 14px; font-weight: 700; color: #111827; margin-top: 4px; }
  .zk-agent-card__price-high { font-size: 12px; font-weight: 400; color: #6b7280; }
  .zk-agent-card__actions { margin-top: 10px; }
  .zk-agent-card__add-btn {
    width: 100%; padding: 8px 16px; font-size: 12px; font-weight: 600;
    border: 1px solid ${primaryColor}; border-radius: 8px; background: transparent;
    color: ${primaryColor}; cursor: pointer; transition: all 150ms ease;
  }
  .zk-agent-card__add-btn:hover { background: ${primaryColor}; color: white; }

  /* ===== Agent Product Detail ===== */
  .zk-agent-detail { margin: 8px 0; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; background: white; }
  .zk-agent-detail__gallery { position: relative; }
  .zk-agent-detail__main-image {
    width: 100%; height: 260px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  .zk-agent-detail__main-image img { width: 100%; height: 100%; object-fit: cover; border-radius: 12px 12px 0 0; }
  .zk-agent-detail__thumbs {
    display: flex; gap: 8px; padding: 10px; overflow-x: auto; scrollbar-width: none;
  }
  .zk-agent-detail__thumbs::-webkit-scrollbar { display: none; }
  .zk-agent-detail__thumb {
    flex: 0 0 56px; width: 56px; height: 56px; border-radius: 8px; overflow: hidden;
    border: 2px solid transparent; cursor: pointer; padding: 0; background: none;
    transition: border-color 150ms ease;
  }
  .zk-agent-detail__thumb--active { border-width: 3px; border-color: ${primaryColor}; }
  .zk-agent-detail__thumb img { width: 100%; height: 100%; object-fit: cover; }
  .zk-agent-detail__info { padding: 16px; }
  .zk-agent-detail__name { font-size: 18px; font-weight: 700; color: #111827; }
  .zk-agent-detail__price { font-size: 20px; font-weight: 700; color: #111827; margin-top: 6px; }
  .zk-agent-detail__price-range { font-size: 14px; font-weight: 400; color: #6b7280; }
  .zk-agent-detail__categories { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
  .zk-agent-detail__cat-tag {
    font-size: 12px; padding: 4px 10px; border-radius: 6px; background: #f3f4f6;
    color: #6b7280; text-transform: capitalize;
  }
  .zk-agent-detail__desc { font-size: 13px; color: #4b5563; margin-top: 10px; line-height: 1.5; }
  .zk-agent-detail__variations { margin-top: 14px; }
  .zk-agent-detail__var-label { font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 8px; text-transform: uppercase; }
  .zk-agent-detail__var-options { display: flex; gap: 8px; flex-wrap: wrap; }
  .zk-var-pill {
    padding: 8px 14px; border: 1px solid #d1d5db; border-radius: 8px; background: white;
    font-size: 13px; font-weight: 500; cursor: pointer; transition: all 150ms ease; color: #374151;
  }
  .zk-var-pill:hover { border-color: ${primaryColor}; }
  .zk-var-pill--active { border-color: ${primaryColor}; background: ${primaryColor}; color: white; }
  .zk-var-pill--disabled { opacity: 0.4; cursor: not-allowed; text-decoration: line-through; }
  .zk-agent-detail__actions { display: flex; gap: 8px; margin-top: 16px; }
  .zk-agent-detail__add-btn {
    flex: 1; height: 44px; padding: 0 16px; font-size: 14px; font-weight: 700; border: none;
    border-radius: 10px; background: ${primaryColor}; color: white; cursor: pointer;
    transition: opacity 150ms ease;
  }
  .zk-agent-detail__add-btn:hover { opacity: 0.9; }
  .zk-agent-detail__add-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .zk-agent-detail__wishlist-btn {
    width: 44px; height: 44px; border: 1px solid #d1d5db; border-radius: 10px;
    background: white; cursor: pointer; display: flex; align-items: center; justify-content: center;
    color: #6b7280; transition: all 150ms ease;
  }
  .zk-agent-detail__wishlist-btn:hover { border-color: #ef4444; color: #ef4444; }

  /* Quantity section (used in product detail) */
  .zk-agent-detail__qty-section { margin-top: 14px; }
  .zk-agent-detail__qty-label {
    font-size: 12px; font-weight: 600; color: #374151; margin-bottom: 8px; text-transform: uppercase;
  }

  /* ===== Agent Cart ===== */
  .zk-agent-cart { margin: 8px 0; border: 1px solid #e5e7eb; border-radius: 12px; background: white; overflow: hidden; }
  .zk-agent-cart--empty { padding: 24px; text-align: center; color: #6b7280; font-size: 14px; }
  .zk-agent-cart__items { padding: 6px; }
  .zk-agent-cart__item {
    display: flex; gap: 12px; padding: 14px; border-bottom: 1px solid #f3f4f6; align-items: center;
    animation: zk-slide-in 250ms ease-out;
  }
  .zk-agent-cart__item:last-child { border-bottom: none; }
  .zk-agent-cart__thumb { width: 56px; height: 56px; border-radius: 8px; object-fit: cover; }
  .zk-agent-cart__item-info { flex: 1; min-width: 0; }
  .zk-agent-cart__item-name { font-size: 14px; font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .zk-agent-cart__item-details { font-size: 11px; color: #6b7280; margin-top: 2px; display: flex; gap: 8px; }
  .zk-agent-cart__item-price { font-size: 14px; font-weight: 700; color: #111827; margin-top: 2px; }
  .zk-agent-cart__item-unit-price { font-size: 11px; color: #6b7280; }
  .zk-agent-cart__item-line {
    display: flex; align-items: center; gap: 8px; margin-top: 4px;
  }
  .zk-agent-cart__remove {
    width: 28px; height: 28px; border: none; background: #fef2f2; border-radius: 50%;
    cursor: pointer; display: flex; align-items: center; justify-content: center; color: #ef4444;
    transition: all 150ms ease;
  }
  .zk-agent-cart__remove:hover { background: #fee2e2; }
  .zk-agent-cart__footer {
    padding: 16px; border-top: 1px solid #e5e7eb;
    background: #f9fafb; border-radius: 0 0 12px 12px;
  }
  .zk-agent-cart__subtotal { display: flex; justify-content: space-between; font-size: 14px; color: #374151; margin-bottom: 12px; }
  .zk-agent-cart__subtotal-price { font-weight: 700; }
  .zk-agent-cart__checkout-btn {
    width: 100%; height: 44px; font-size: 14px; font-weight: 700; border: none;
    border-radius: 10px; background: ${primaryColor}; color: white; cursor: pointer;
    transition: opacity 150ms ease;
  }
  .zk-agent-cart__checkout-btn:hover { opacity: 0.9; }

  /* ===== Wishlist ===== */
  .zk-wishlist { margin: 8px 0; border: 1px solid #e5e7eb; border-radius: 12px; background: white; overflow: hidden; }
  .zk-wishlist--empty { padding: 24px; text-align: center; color: #9ca3af; font-size: 14px; }
  .zk-wishlist__header { padding: 14px 16px; font-size: 15px; font-weight: 600; color: #374151; border-bottom: 1px solid #f3f4f6; }
  .zk-wishlist__items { padding: 6px; }
  .zk-wishlist__item { display: flex; gap: 12px; padding: 14px; align-items: center; border-bottom: 1px solid #f3f4f6; }
  .zk-wishlist__item:last-child { border-bottom: none; }
  .zk-wishlist__thumb { width: 48px; height: 48px; border-radius: 8px; object-fit: cover; }
  .zk-wishlist__info { flex: 1; min-width: 0; }
  .zk-wishlist__name { font-size: 13px; font-weight: 600; color: #111827; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .zk-wishlist__price { font-size: 13px; color: #374151; margin-top: 2px; }
  .zk-wishlist__actions { display: flex; gap: 6px; }
  .zk-wishlist__cart-btn {
    padding: 6px 14px; font-size: 12px; border: 1px solid ${primaryColor}; border-radius: 8px;
    background: transparent; color: ${primaryColor}; cursor: pointer;
    transition: all 150ms ease;
  }
  .zk-wishlist__cart-btn:hover { background: ${primaryColor}; color: white; }
  .zk-wishlist__remove-btn {
    width: 24px; height: 24px; border: none; background: none; cursor: pointer; color: #9ca3af;
    display: flex; align-items: center; justify-content: center; border-radius: 50%;
    transition: all 150ms ease;
  }
  .zk-wishlist__remove-btn:hover { background: #fef2f2; color: #ef4444; }

  /* ===== Checkout Flow ===== */
  .zk-checkout { margin: 8px 0; }
  .zk-checkout__steps {
    display: flex; align-items: center; gap: 8px; margin-bottom: 16px; padding: 14px;
    background: #f9fafb; border-radius: 12px;
  }
  .zk-checkout__step {
    display: flex; align-items: center; gap: 6px; font-size: 12px; color: #9ca3af;
  }
  .zk-checkout__step--active { color: ${primaryColor}; font-weight: 700; }
  .zk-checkout__step--done { color: #10b981; }
  .zk-checkout__step-num {
    width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; font-size: 12px; font-weight: 700; border: 2px solid currentColor;
  }
  .zk-checkout__step--active .zk-checkout__step-num {
    background: ${primaryColor}; color: white; border-color: ${primaryColor};
    box-shadow: 0 0 0 4px ${primaryColor}20;
    animation: zk-step-pulse 2s ease-in-out infinite;
  }
  .zk-checkout__step--done .zk-checkout__step-num { background: #10b981; color: white; border-color: #10b981; }
  .zk-checkout__step-line { flex: 1; height: 2px; background: #e5e7eb; }
  .zk-checkout__summary {
    background: #f9fafb; border-radius: 12px; padding: 16px; margin-bottom: 14px; font-size: 13px;
  }
  .zk-checkout__item {
    display: flex; justify-content: space-between; padding: 6px 0; color: #374151;
  }
  .zk-checkout__total {
    display: flex; justify-content: space-between; padding-top: 10px;
    margin-top: 10px; border-top: 2px solid #e5e7eb; font-size: 16px; font-weight: 700;
  }
  .zk-checkout__error {
    background: #fef2f2; color: #dc2626; padding: 12px 16px; border-radius: 10px;
    font-size: 13px; margin-bottom: 12px; border-left: 3px solid #dc2626;
  }

  /* ===== Shipping Form ===== */
  .zk-shipping { margin: 0; }
  .zk-shipping__title { font-size: 14px; font-weight: 700; margin-bottom: 14px; color: #111827; }
  .zk-shipping__label {
    display: block; font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 6px;
  }
  .zk-shipping__field { margin-bottom: 16px; }
  .zk-shipping__field input, .zk-shipping__field select {
    width: 100%; height: 42px; padding: 0 12px; border: 1px solid #d1d5db; border-radius: 10px;
    font-size: 14px; background: white; color: #111827; box-sizing: border-box;
    font-family: inherit; transition: all 150ms ease;
  }
  .zk-shipping__field input:focus, .zk-shipping__field select:focus {
    outline: none; border-color: ${primaryColor}; box-shadow: 0 0 0 3px ${primaryColor}15;
  }
  .zk-shipping__input--error { border-color: #dc2626 !important; }
  .zk-shipping__error {
    font-size: 12px; color: #dc2626; margin-top: 4px; display: flex; align-items: center; gap: 4px;
  }
  .zk-shipping__error::before {
    content: ''; width: 4px; height: 4px; border-radius: 50%; background: #dc2626; flex-shrink: 0;
  }
  .zk-shipping__row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .zk-shipping__submit {
    width: 100%; height: 44px; background: ${primaryColor}; color: white; border: none;
    border-radius: 10px; font-size: 14px; font-weight: 700; cursor: pointer; margin-top: 8px;
    transition: opacity 150ms ease;
  }
  .zk-shipping__submit:hover { opacity: 0.9; }
  .zk-shipping__submit:disabled { opacity: 0.5; cursor: not-allowed; }

  /* ===== Payment Selector ===== */
  .zk-payment { margin: 0; }
  .zk-payment__title { font-size: 14px; font-weight: 700; margin-bottom: 4px; color: #111827; }
  .zk-payment__total { font-size: 13px; color: #6b7280; margin-bottom: 14px; }
  .zk-payment__options { display: flex; flex-direction: column; gap: 10px; margin-bottom: 14px; }
  .zk-payment__option {
    padding: 16px; border: 2px solid #e5e7eb; border-radius: 12px; background: white;
    cursor: pointer; text-align: left; transition: all 150ms ease;
  }
  .zk-payment__option:hover { border-color: #9ca3af; background: #f9fafb; }
  .zk-payment__option--selected {
    border-color: ${primaryColor}; background: ${primaryColor}08;
    box-shadow: 0 0 0 1px ${primaryColor}20;
  }
  .zk-payment__option-name { font-size: 15px; font-weight: 600; color: #111827; }
  .zk-payment__option-desc { font-size: 12px; color: #6b7280; margin-top: 3px; }
  .zk-payment__pay-btn {
    width: 100%; height: 48px; background: ${primaryColor}; color: white; border: none;
    border-radius: 10px; font-size: 15px; font-weight: 700; cursor: pointer;
    transition: opacity 150ms ease;
  }
  .zk-payment__pay-btn:hover { opacity: 0.9; }
  .zk-payment__pay-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .zk-payment__secure {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    font-size: 12px; color: #6b7280; margin-top: 16px;
  }
  .zk-payment__logo {
    display: flex; align-items: center; gap: 8px;
  }
  .zk-payment__logo svg { flex-shrink: 0; width: 32px; height: 32px; }

  /* ===== Order Confirmation ===== */
  .zk-order-confirm {
    margin: 8px 0; border: 1px solid #bbf7d0; border-radius: 12px; background: #f0fdf4;
    padding: 28px; text-align: center;
  }
  .zk-order-confirm__icon { margin-bottom: 16px; animation: zk-check-pop 500ms ease-out; }
  .zk-order-confirm__title { font-size: 20px; font-weight: 700; color: #15803d; }
  .zk-order-confirm__id {
    font-size: 14px; color: #4b5563; margin-top: 8px; font-family: monospace;
    display: inline-block; background: #dcfce7; padding: 6px 12px; border-radius: 8px;
  }
  .zk-order-confirm__total { font-size: 16px; font-weight: 700; color: #111827; margin-top: 12px; }
  .zk-order-confirm__msg { font-size: 13px; color: #6b7280; margin-top: 12px; line-height: 1.5; }
  .zk-order-confirm__continue {
    margin-top: 16px; padding: 10px 24px; font-size: 14px; font-weight: 600;
    border: 1px solid ${primaryColor}; border-radius: 10px;
    background: transparent; color: ${primaryColor}; cursor: pointer;
    transition: all 150ms ease;
  }
  .zk-order-confirm__continue:hover { background: ${primaryColor}; color: white; }

  /* ===== Cart Confirmation (Add to Cart) ===== */
  .zk-cart-confirm {
    margin: 8px 0; border: 1px solid #bbf7d0; border-radius: 12px; background: #f0fdf4;
    overflow: hidden; animation: zk-slide-in 250ms ease-out;
  }
  .zk-cart-confirm__body {
    display: flex; gap: 12px; padding: 14px; align-items: center;
  }
  .zk-cart-confirm__thumb {
    width: 52px; height: 52px; border-radius: 8px; object-fit: cover; flex-shrink: 0;
  }
  .zk-cart-confirm__info { flex: 1; min-width: 0; }
  .zk-cart-confirm__badge {
    display: flex; align-items: center; gap: 5px;
    font-size: 12px; font-weight: 700; color: #16a34a; margin-bottom: 2px;
  }
  .zk-cart-confirm__name {
    font-size: 14px; font-weight: 600; color: #111827;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .zk-cart-confirm__variation { font-size: 12px; color: #6b7280; margin-top: 1px; }
  .zk-cart-confirm__price { font-size: 13px; font-weight: 500; color: #374151; margin-top: 2px; }
  .zk-cart-confirm__footer {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 14px; border-top: 1px solid #bbf7d0; background: #ecfdf5;
  }
  .zk-cart-confirm__summary { font-size: 12px; color: #374151; font-weight: 500; }
  .zk-cart-confirm__actions { display: flex; gap: 8px; }
  .zk-cart-confirm__view-btn {
    padding: 6px 14px; font-size: 12px; font-weight: 600;
    border: 1px solid ${primaryColor}; border-radius: 8px;
    background: ${primaryColor}; color: white; cursor: pointer;
    transition: opacity 150ms ease;
  }
  .zk-cart-confirm__view-btn:hover { opacity: 0.9; }
  .zk-cart-confirm__continue-btn {
    padding: 6px 14px; font-size: 12px; font-weight: 500;
    border: 1px solid #d1d5db; border-radius: 8px;
    background: white; color: #374151; cursor: pointer;
    transition: all 150ms ease;
  }
  .zk-cart-confirm__continue-btn:hover { background: #f9fafb; border-color: #9ca3af; }

  /* ===== Agent Categories ===== */
  .zk-agent-categories { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }

  /* ===== Payment Waiting State ===== */
  @keyframes zk-spin { to { transform: rotate(360deg); } }
  @keyframes zk-pulse-text { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
  .zk-payment-waiting {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 36px 16px; text-align: center;
  }
  .zk-payment-waiting__spinner {
    width: 48px; height: 48px; border: 3px solid #e5e7eb;
    border-top-color: ${primaryColor}; border-radius: 50%;
    animation: zk-spin 0.7s linear infinite; margin-bottom: 20px;
  }
  .zk-payment-waiting__text {
    font-size: 16px; font-weight: 600; color: #111827; margin-bottom: 6px;
    animation: zk-pulse-text 2s ease-in-out infinite;
  }
  .zk-payment-waiting__sub {
    font-size: 13px; color: #6b7280; margin-bottom: 20px;
  }
  .zk-payment-waiting__retry {
    font-size: 14px; color: ${primaryColor}; background: none; border: none;
    cursor: pointer; text-decoration: underline; margin-bottom: 10px;
  }
  .zk-payment-waiting__cancel {
    font-size: 14px; color: #6b7280; background: none; border: 1px solid #d1d5db;
    border-radius: 10px; padding: 8px 20px; cursor: pointer; transition: all 150ms ease;
  }
  .zk-payment-waiting__cancel:hover { background: #f9fafb; }

  /* ===== Payment Failed State ===== */
  .zk-payment-failed {
    display: flex; flex-direction: column; align-items: center; padding: 28px 16px;
    text-align: center;
  }
  .zk-payment-failed__icon { margin-bottom: 16px; color: #dc2626; }
  .zk-payment-failed__title {
    font-size: 18px; font-weight: 700; color: #dc2626; margin-bottom: 6px;
  }
  .zk-payment-failed__msg {
    font-size: 13px; color: #6b7280; margin-bottom: 20px;
  }
  .zk-payment-failed__retry {
    padding: 10px 24px; font-size: 14px; font-weight: 600; border: none;
    border-radius: 10px; background: ${primaryColor}; color: white; cursor: pointer;
    transition: opacity 150ms ease;
  }
  .zk-payment-failed__retry:hover { opacity: 0.9; }

  /* ===== Animations ===== */
  @keyframes zk-fade-in { from { opacity: 0; } to { opacity: 1; } }
  @keyframes zk-shimmer {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
  }
  @keyframes zk-slide-in {
    from { opacity: 0; transform: translateX(-12px); }
    to { opacity: 1; transform: translateX(0); }
  }
  @keyframes zk-step-pulse {
    0%,100% { box-shadow: 0 0 0 0 ${primaryColor}44; }
    50% { box-shadow: 0 0 0 4px ${primaryColor}22; }
  }
  @keyframes zk-check-pop {
    0% { transform: scale(0); opacity: 0; }
    60% { transform: scale(1.2); }
    100% { transform: scale(1); opacity: 1; }
  }

  .zk-agent-card__image--skeleton {
    position: relative; overflow: hidden; background: #f3f4f6;
  }
  .zk-agent-card__image--skeleton::after {
    content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
    animation: zk-shimmer 1.5s infinite;
  }

  /* ===== Quantity Controls ===== */
  .zk-qty-control {
    display: inline-flex; align-items: center; border: 1px solid #d1d5db;
    border-radius: 8px; overflow: hidden;
  }
  .zk-qty-control__btn {
    width: 32px; height: 32px; border: none; background: #f9fafb;
    cursor: pointer; font-size: 16px; font-weight: 600; color: #374151;
    display: flex; align-items: center; justify-content: center;
    transition: background 150ms ease;
  }
  .zk-qty-control__btn:hover { background: #f3f4f6; }
  .zk-qty-control__btn:disabled { opacity: 0.3; cursor: not-allowed; }
  .zk-qty-control__count {
    width: 36px; text-align: center; font-size: 14px; font-weight: 600;
    color: #111827; border-left: 1px solid #d1d5db; border-right: 1px solid #d1d5db;
    line-height: 32px;
  }

  /* ===== Cart Badge ===== */
  .zk-cart-badge {
    position: relative; display: inline-flex; align-items: center; justify-content: center;
    cursor: pointer; background: none; border: none; padding: 0;
  }
  .zk-cart-badge__count {
    position: absolute; top: -6px; right: -8px; min-width: 16px; height: 16px;
    background: #ef4444; color: white; font-size: 10px; font-weight: 700;
    border-radius: 8px; display: flex; align-items: center; justify-content: center;
    padding: 0 4px; line-height: 1;
  }

  /* ===== Back to Results Link ===== */
  .zk-agent-detail__back {
    display: inline-flex; align-items: center; gap: 4px; padding: 10px 14px;
    font-size: 13px; font-weight: 500; color: #6b7280; cursor: pointer; background: none; border: none;
    transition: color 150ms ease;
  }
  .zk-agent-detail__back:hover { color: ${primaryColor}; }

  /* ===== Empty State Icons ===== */
  .zk-empty-state {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 28px 16px; text-align: center;
  }
  .zk-empty-state__icon { margin-bottom: 10px; color: #d1d5db; }
  .zk-empty-state__text { font-size: 14px; color: #9ca3af; }

  /* ===== Mobile Overrides ===== */
  .zk-mobile .zk-agent-card { flex: 0 0 170px; }
  .zk-mobile .zk-shipping__row { grid-template-columns: 1fr; }
  .zk-mobile .zk-payment__options { flex-direction: column; }
`
