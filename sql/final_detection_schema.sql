-- MySQL schema for stone curtain wall stain detection
-- Idempotent: safe to run multiple times

create database if not exists `stain`
  default character set utf8mb4
  default collate utf8mb4_unicode_ci;

use `stain`;

drop table if exists `result_regions`;
drop table if exists `detection_results`;
drop table if exists `task_images`;
drop table if exists `inspection_tasks`;

create table `inspection_tasks` (
  `id` bigint unsigned not null auto_increment,
  `user_id` varchar(64) not null,
  `building_name` varchar(255) not null,
  `location_floor` int null,
  `location_section` varchar(255) null,
  `description` text null,
  `status` enum('pending', 'processing', 'done', 'failed') not null default 'pending',
  `summary` text null,
  `stain_detected` tinyint(1) null,
  `stain_type` varchar(255) null,
  `affected_area_percentage` decimal(6, 2) null,
  `error_message` text null,
  `created_at` datetime not null default current_timestamp,
  `updated_at` datetime not null default current_timestamp on update current_timestamp,
  primary key (`id`),
  key `idx_inspection_tasks_user_created` (`user_id`, `created_at` desc),
  key `idx_inspection_tasks_user_status_created` (`user_id`, `status`, `created_at` desc),
  key `idx_inspection_tasks_status` (`status`),
  key `idx_inspection_tasks_building_name` (`building_name`)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table `task_images` (
  `id` bigint unsigned not null auto_increment,
  `task_id` bigint unsigned not null,
  `user_id` varchar(64) not null,
  `image_name` varchar(255) null,
  `original_image_path` varchar(500) not null,
  `processed_image_path` varchar(500) null,
  `mime_type` varchar(100) null,
  `file_size` bigint unsigned null,
  `created_at` datetime not null default current_timestamp,
  primary key (`id`),
  key `idx_task_images_task_id` (`task_id`),
  key `idx_task_images_user_id` (`user_id`),
  constraint `fk_task_images_task_id` foreign key (`task_id`) references `inspection_tasks` (`id`) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table `detection_results` (
  `id` bigint unsigned not null auto_increment,
  `task_id` bigint unsigned not null,
  `user_id` varchar(64) not null,
  `status` enum('pending', 'processing', 'done', 'failed') not null default 'pending',
  `summary` text null,
  `metrics` json null,
  `error_message` text null,
  `created_at` datetime not null default current_timestamp,
  `updated_at` datetime not null default current_timestamp on update current_timestamp,
  `processed_at` datetime null,
  primary key (`id`),
  unique key `uq_detection_results_task_id` (`task_id`),
  key `idx_detection_results_user_id` (`user_id`),
  constraint `fk_detection_results_task_id` foreign key (`task_id`) references `inspection_tasks` (`id`) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table `result_regions` (
  `id` bigint unsigned not null auto_increment,
  `task_id` bigint unsigned not null,
  `label` varchar(255) not null,
  `confidence` decimal(5, 4) not null,
  `x1` decimal(8, 5) not null,
  `y1` decimal(8, 5) not null,
  `x2` decimal(8, 5) not null,
  `y2` decimal(8, 5) not null,
  `created_at` datetime not null default current_timestamp,
  primary key (`id`),
  key `idx_result_regions_task_id` (`task_id`),
  constraint `fk_result_regions_task_id` foreign key (`task_id`) references `inspection_tasks` (`id`) on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;
