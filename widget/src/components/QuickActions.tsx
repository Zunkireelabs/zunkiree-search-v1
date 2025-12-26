import React from 'react';
import { QuickActionsProps } from '../types';

export const QuickActions: React.FC<QuickActionsProps> = ({
  actions,
  onActionClick,
}) => {
  if (!actions || actions.length === 0) {
    return null;
  }

  return (
    <div className="zk-quick-actions" role="group" aria-label="Quick search suggestions">
      {actions.map((action, index) => (
        <button
          key={index}
          className="zk-chip"
          onClick={() => onActionClick(action)}
          type="button"
        >
          {action}
        </button>
      ))}
    </div>
  );
};

export default QuickActions;
