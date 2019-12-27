-- phpMyAdmin SQL Dump
-- version 4.6.5.2
-- https://www.phpmyadmin.net/
--
-- Host: localhost
-- Generation Time: Apr 24, 2019 at 03:25 PM
-- Server version: 10.3.10-MariaDB-log
-- PHP Version: 5.6.38-pl0-gentoo

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `abcmartin`
--

-- --------------------------------------------------------

--
-- Table structure for table `block`
--

CREATE TABLE `block` (
  `hash` char(64) NOT NULL,
  `strippedsize` int(11) NOT NULL,
  `size` int(11) NOT NULL,
  `weight` int(11) NOT NULL,
  `height` int(11) NOT NULL,
  `version` int(11) NOT NULL,
  `versionHex` int(11) NOT NULL,
  `merkleroot` char(64) NOT NULL,
  `time` int(11) NOT NULL,
  `mediantime` int(11) NOT NULL,
  `nonce` bigint(20) NOT NULL,
  `bits` varchar(10) NOT NULL,
  `difficulty` double NOT NULL,
  `chainwork` char(64) NOT NULL,
  `nTx` int(11) NOT NULL,
  `previousblockhash` char(64) NOT NULL,
  `nextblockhash` char(64) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `block_hashrate`
--

CREATE TABLE `block_hashrate` (
  `height` int(11) NOT NULL,
  `hashrate` double NOT NULL,
  `difficulty` double NOT NULL,
  `algo` varchar(16) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8 ROW_FORMAT=COMPACT;

-- --------------------------------------------------------

--
-- Table structure for table `block_reward`
--

CREATE TABLE `block_reward` (
  `height` int(11) NOT NULL,
  `amount` bigint(20) NOT NULL,
  `pow` bigint(20) DEFAULT NULL,
  `pos` bigint(20) DEFAULT NULL,
  `mn` bigint(20) DEFAULT NULL,
  `dev` bigint(20) DEFAULT NULL,
  `algo` varchar(16) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `block_rewards`
--

CREATE TABLE `block_rewards` (
  `id` int(11) NOT NULL,
  `hash` varchar(1024) NOT NULL,
  `algo` varchar(64) NOT NULL,
  `rewards` float NOT NULL,
  `difficulty` float NOT NULL,
  `hashrate` float DEFAULT NULL,
  `reward_per_mh` double DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `daily_price`
--

CREATE TABLE `daily_price` (
  `date` date NOT NULL,
  `close` bigint(20) NOT NULL,
  `high` bigint(20) NOT NULL,
  `low` bigint(20) NOT NULL,
  `volume` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

--
-- Dumping data for table `daily_price`
--

INSERT INTO `daily_price` (`date`, `close`, `high`, `low`, `volume`) VALUES
('2019-04-04', 400, 420, 198, 13760),
('2019-04-05', 459, 700, 237, 22900),
('2019-04-06', 378, 1910, 455, 12500),
('2019-04-07', 531, 1149, 455, 8600),
('2019-04-08', 614, 458, 884, 10900),
('2019-04-09', 471, 811, 458, 2238339),
('2019-04-19', 1213, 1318, 1212, 10158559);

-- --------------------------------------------------------

--
-- Table structure for table `daily_supply`
--

CREATE TABLE `daily_supply` (
  `id` int(11) NOT NULL,
  `height` int(11) NOT NULL,
  `total` bigint(20) NOT NULL,
  `time` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `mining_status`
--

CREATE TABLE `mining_status` (
  `algo` varchar(64) NOT NULL,
  `difficulty` float NOT NULL,
  `hashrate` float DEFAULT NULL,
  `blocks` int(11) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- --------------------------------------------------------

--
-- Table structure for table `transaction`
--

CREATE TABLE `transaction` (
  `txid` char(64) NOT NULL,
  `hash` char(64) NOT NULL,
  `version` smallint(6) NOT NULL,
  `size` int(11) NOT NULL,
  `vsize` int(11) NOT NULL,
  `weight` int(11) NOT NULL,
  `locktime` int(11) NOT NULL,
  `vin` mediumblob NOT NULL,
  `vout` mediumblob NOT NULL,
  `blockhash` char(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

--
-- Indexes for dumped tables
--

--
-- Indexes for table `block`
--
ALTER TABLE `block`
  ADD PRIMARY KEY (`hash`),
  ADD UNIQUE KEY `height_2` (`height`),
  ADD KEY `height` (`height`);

--
-- Indexes for table `block_reward`
--
ALTER TABLE `block_reward`
  ADD PRIMARY KEY (`height`);

--
-- Indexes for table `daily_price`
--
ALTER TABLE `daily_price`
  ADD PRIMARY KEY (`date`);

--
-- Indexes for table `daily_supply`
--
ALTER TABLE `daily_supply`
  ADD PRIMARY KEY (`id`);

--
-- Indexes for table `mining_status`
--
ALTER TABLE `mining_status`
  ADD PRIMARY KEY (`algo`);

--
-- Indexes for table `transaction`
--
ALTER TABLE `transaction`
  ADD PRIMARY KEY (`txid`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `daily_supply`
--
ALTER TABLE `daily_supply`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=69;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
