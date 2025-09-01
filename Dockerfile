# Use official PHP image with Apache
FROM php:8.4-apache


ARG http_proxy
ARG https_proxy

ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}


# Download and install the install-php-extensions script
# https://github.com/mlocati/docker-php-extension-installer
RUN curl -sSL https://github.com/mlocati/docker-php-extension-installer/releases/latest/download/install-php-extensions -o /usr/local/bin/install-php-extensions \
    && chmod +x /usr/local/bin/install-php-extensions

# Configure PEAR
RUN if [ -n "${http_proxy}" ]; then pear config-set http_proxy ${http_proxy}; fi && \
    pear config-set php_ini $PHP_INI_DIR/php.ini


# Install system dependencies for PostgreSQL, Xdebug, and cron
RUN apt-get update \
    && apt-get install -y libpq-dev cron curl \
    && pecl install xdebug \
    && docker-php-ext-enable xdebug \
    && docker-php-ext-install pdo pdo_pgsql

# Xdebug configuration
COPY ./build_config/xdebug.ini /usr/local/etc/php/conf.d/xdebug.ini

# Enable Apache modules for .htaccess functionality
RUN a2enmod rewrite headers expires deflate

# Set working directory
WORKDIR /var/www/html

# Copy project files
COPY . /var/www/html

# Apache vhost for serving docs and OpenAPI spec
COPY ./build_config/apache-masterdb.conf /etc/apache2/sites-available/masterdb.conf
RUN a2dissite 000-default.conf \
    && a2ensite masterdb.conf

# Copy and make the entrypoint script executable
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set permissions (optional, for dev)
RUN chown -R www-data:www-data /var/www/html

# Expose port 80 (Apache default)
EXPOSE 80

# Use our custom entrypoint script
CMD ["/usr/local/bin/docker-entrypoint.sh"]
