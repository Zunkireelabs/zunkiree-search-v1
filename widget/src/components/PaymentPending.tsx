interface PaymentPendingProps {
  checkoutUrl?: string
}

export function PaymentPending({ checkoutUrl }: PaymentPendingProps) {
  return (
    <div className="zk-payment-pending">
      <div className="zk-payment-pending__spinner">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
        </svg>
      </div>
      <div className="zk-payment-pending__text">Redirecting to secure payment...</div>
      {checkoutUrl && (
        <a
          href={checkoutUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="zk-payment-pending__link"
        >
          Click here if not redirected
        </a>
      )}
    </div>
  )
}
