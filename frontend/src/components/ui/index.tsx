import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: React.ReactNode;
  fullWidth?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  fullWidth = false,
  children,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center font-medium transition-all duration-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed';
  
  const variants = {
    primary: 'bg-primary hover:bg-primary-hover text-white shadow-sm hover:shadow focus:ring-primary/50',
    secondary: 'bg-white border border-border hover:bg-gray-50 text-text-primary shadow-sm hover:shadow focus:ring-gray-200',
    outline: 'border border-border bg-transparent hover:bg-gray-50 text-text-primary focus:ring-gray-200',
    ghost: 'hover:bg-gray-100 text-text-muted hover:text-text-primary focus:ring-gray-200',
    danger: 'bg-error hover:bg-red-600 text-white shadow-sm hover:shadow focus:ring-error/50',
  };
  
  const sizes = {
    sm: 'px-3 py-1.5 text-sm gap-1.5',
    md: 'px-4 py-2 text-sm gap-2',
    lg: 'px-6 py-3 text-base gap-2.5',
  };
  
  return (
    <button
      className={`
        ${baseStyles}
        ${variants[variant]}
        ${sizes[size]}
        ${fullWidth ? 'w-full' : ''}
        ${className}
      `}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      ) : icon}
      {children}
    </button>
  );
};

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export const Card: React.FC<CardProps> = ({ 
  children, 
  className = '', 
  hover = false,
  padding = 'md' 
}) => {
  const paddingStyles = {
    none: '',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8',
  };
  
  return (
    <div className={`
      bg-card rounded-xl border border-border shadow-sm
      ${hover ? 'hover:shadow-md transition-shadow duration-200' : ''}
      ${paddingStyles[padding]}
      ${className}
    `}>
      {children}
    </div>
  );
};

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'error' | 'warning' | 'info' | 'neutral';
  size?: 'sm' | 'md';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ 
  children, 
  variant = 'neutral',
  size = 'sm',
  className = ''
}) => {
  const variants = {
    success: 'bg-success/10 text-success border-success/20',
    error: 'bg-error/10 text-error border-error/20',
    warning: 'bg-warning/10 text-warning border-warning/20',
    info: 'bg-primary/10 text-primary border-primary/20',
    neutral: 'bg-gray-100 text-text-muted border-gray-200',
  };
  
  const sizes = {
    sm: 'px-2.5 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
  };
  
  return (
    <span className={`
      inline-flex items-center font-medium rounded-full border
      ${variants[variant]}
      ${sizes[size]}
      ${className}
    `}>
      {children}
    </span>
  );
};

interface ProgressBarProps {
  value: number;
  max?: number;
  color?: 'violet' | 'green' | 'blue' | 'amber';
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ 
  value, 
  max = 100,
  color = 'violet',
  size = 'md',
  showLabel = false 
}) => {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
  
  const colors = {
    violet: 'bg-primary',
    green: 'bg-success',
    blue: 'bg-primary', // Map blue to primary for consistency
    amber: 'bg-warning',
  };
  
  const heights = {
    sm: 'h-1',
    md: 'h-2',
    lg: 'h-3',
  };
  
  return (
    <div className="w-full">
      <div className={`w-full bg-gray-100 rounded-full overflow-hidden ${heights[size]}`}>
        <div 
          className={`${colors[color]} h-full transition-all duration-500 ease-out rounded-full`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <div className="text-xs text-text-muted mt-1.5 text-center font-medium">
          {Math.round(percentage)}%
        </div>
      )}
    </div>
  );
};

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  trend?: {
    value: number;
    direction: 'up' | 'down';
  };
  color?: 'violet' | 'green' | 'blue' | 'amber' | 'red' | 'gray';
}

export const StatCard: React.FC<StatCardProps> = ({ 
  label, 
  value, 
  icon,
  trend,
  color = 'violet' 
}) => {
  // We can add a subtle indicator line or icon color instead of full background
  const iconColors = {
    violet: 'text-primary bg-primary/10',
    green: 'text-success bg-success/10',
    blue: 'text-primary bg-primary/10',
    amber: 'text-warning bg-warning/10',
    red: 'text-error bg-error/10',
    gray: 'text-text-muted bg-gray-100',
  };

  return (
    <div className="bg-card rounded-xl border border-border p-6 shadow-sm hover:shadow-md transition-shadow duration-200">
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm font-medium text-text-muted">{label}</span>
        {icon && (
          <div className={`p-2 rounded-lg ${iconColors[color]}`}>
            {React.isValidElement(icon)
              ? React.cloneElement(icon as React.ReactElement<{ className?: string }>, { className: 'w-4 h-4' })
              : icon}
          </div>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <div className="text-3xl font-bold text-text-primary">{value}</div>
        {trend && (
          <span className={`text-sm font-medium ${
            trend.direction === 'up' ? 'text-success' : 'text-error'
          }`}>
            {trend.direction === 'up' ? '↑' : '↓'} {Math.abs(trend.value)}%
          </span>
        )}
      </div>
    </div>
  );
};

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export const EmptyState: React.FC<EmptyStateProps> = ({ 
  icon, 
  title, 
  description,
  action 
}) => {
  return (
    <div className="text-center py-16 px-4">
      {icon && (
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-50 text-text-muted mb-6 border border-border">
          {icon}
        </div>
      )}
      <h3 className="text-lg font-semibold text-text-primary mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-text-muted mb-8 max-w-md mx-auto leading-relaxed">{description}</p>
      )}
      {action && (
        <Button onClick={action.onClick}>{action.label}</Button>
      )}
    </div>
  );
};

interface FloatingActionButtonProps {
  onClick: () => void;
  icon: React.ReactNode;
  label?: string;
  position?: 'bottom-right' | 'bottom-left';
}

export const FloatingActionButton: React.FC<FloatingActionButtonProps> = ({ 
  onClick, 
  icon, 
  label,
  position = 'bottom-right' 
}) => {
  const positions = {
    'bottom-right': 'bottom-8 right-8',
    'bottom-left': 'bottom-8 left-8',
  };
  
  return (
    <button
      onClick={onClick}
      className={`
        fixed ${positions[position]} z-50
        inline-flex items-center gap-2
        bg-primary hover:bg-primary-hover text-white
        px-6 py-4 rounded-full shadow-lg hover:shadow-xl
        transition-all duration-200 transform hover:scale-105
        focus:outline-none focus:ring-2 focus:ring-primary/50 focus:ring-offset-2
      `}
    >
      {icon}
      {label && <span className="font-medium">{label}</span>}
    </button>
  );
};
